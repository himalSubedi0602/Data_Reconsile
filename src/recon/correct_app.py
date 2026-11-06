"""The tool: home screen (projects, setup), then the correction screen. Run from the project root:

    .venv/bin/streamlit run src/recon/correct_app.py
"""

import re
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from recon import home
from recon.config import load_config
from recon.corrections import STATUSES, Project

st.set_page_config(page_title="Survey corrections", layout="wide")


@st.cache_resource
def project(root: str) -> Project:
    return Project(config=load_config(Path(root) / "config/project.json"))


if "project" not in st.session_state:                     # no project open: home screen
    home.page()
    st.stop()
p = project(st.session_state["project"])
surveys = p.surveys()
A, B = p.names                                            # the two people who typed the surveys in
TEAM = p.decisions_label                                  # who made the decisions, e.g. "W&J"
EXAMPLE = p.config.code_example

# ------------------------------------------------------------ left: find a survey
FILTERS = {
    f"Flagged ({A} and {B} disagree)": surveys["differences"] > 0,
    f"{TEAM} decision": surveys["wj"] > 0,
    "Not started": surveys["status"] == "not started",
    "In progress": surveys["status"] == "in progress",
    "Done": surveys["status"] == "done",
    "All surveys": surveys["survey_code"] != "",
}
with st.sidebar:
    if st.button("← All projects"):
        st.session_state.pop("project")
        st.session_state.pop("made", None)
        st.rerun()
    st.header(p.config.survey_name)
    shown = surveys[FILTERS[st.selectbox("Show", list(FILTERS), index=list(FILTERS).index("All surveys"))]]
    # Survey number = the last digits of the well-formed code: 1-0235 -> 235 (typo codes: "All numbers" only).
    number = surveys["survey_code"].map(lambda c: int(re.findall(r"\d+", n)[-1]) if (n := p.config.survey_number(c)) else -1)
    ranges = {"All numbers": (-1, 10**9)} | {
        f"{0 if i == 0 else i * 200 + 1}–{(i + 1) * 200}": (0 if i == 0 else i * 200 + 1, (i + 1) * 200)
        for i in range(number.max() // 200 + 1)}
    low, high = ranges[st.selectbox("Survey numbers", list(ranges))]
    shown = shown[number[shown.index].between(low, high)]
    find = st.text_input("Find a survey code (within the list above)", placeholder=f"e.g. {EXAMPLE}")
    find = re.sub(rf"[\s-]*({A}|{B})\s*$", "", find.strip(), flags=re.I)    # "2-2177-444-CH" -> "2-2177-444"
    if find:
        shown = shown[shown["survey_code"].str.contains(find, regex=False)]
    st.caption(f"{len(shown)} surveys · {(shown['status'] == 'done').sum()} done")
    if shown.empty:
        st.info("No survey matches these filters.")
        st.stop()
    labels = {r.survey_code: f"{r.survey_code}  ·  {r.entered_by}  ·  ⚠ {r.differences}"
              + (f"  ⚑ {r.wj}" if r.wj else "") + f"  ·  {r.status}" for r in shown.itertuples()}
    codes = list(labels)
    if "go_to" in st.session_state:                       # jump to a survey just given its own code
        st.session_state["survey"] = st.session_state.pop("go_to")
    if st.session_state.get("survey") not in codes:
        st.session_state["survey"] = codes[0]
    code = st.selectbox("Pick a survey from the list", codes, key="survey", format_func=labels.get)

    with st.expander("Enter a new survey (not typed in yet)"):
        new_survey = st.text_input("Survey code", placeholder=f"e.g. {EXAMPLE}", key="new_survey_code")
        if st.button("Start a blank survey") and new_survey.strip():
            try:
                p.new_survey(new_survey)
            except ValueError as e:
                st.error(str(e))
            else:
                st.session_state["go_to"] = new_survey.strip()
                st.rerun()

    st.divider()
    st.subheader("Results")
    done, open_ = (surveys["status"] == "done").sum(), (surveys["status"] == "in progress").sum()
    st.caption(f"{done} surveys done · {open_} in progress (not exported until marked done)")
    name = st.text_input("Name for the files", f"round1_{date.today()}")
    if st.button("Export corrected CSV (done surveys)", use_container_width=True):
        n = p.export(path := p.store / f"corrected_{name}.csv")
        st.session_state["made"] = (f"Exported {n} surveys.", path)
    if st.button("Make random check sheet (10 surveys)", use_container_width=True):
        picked = p.random_check(path := p.store / f"random_check_{name}.xlsx")
        st.session_state["made"] = (f"Picked {', '.join(picked)}.", path)
    if "made" in st.session_state:                        # also kept in the project's data/corrections/
        note, path = st.session_state["made"]
        st.success(note)
        st.download_button(f"⬇ Download {path.name}", path.read_bytes(), path.name, use_container_width=True)

# ------------------------------------------------------------ right: the survey
same = [c for c in surveys["survey_code"] if p.number(c) == p.number(code)]     # e.g. 3-2790 and 3-2790-96
if len(same) > 1:
    code = st.radio("Codes with this survey number:", same, same.index(code), horizontal=True, key=f"code|{code}")
info = surveys.set_index("survey_code").loc[code]
available = list(p.starts[code])                         # every entry with this code: HS, CH, online, used or set aside
compared = all(n in available for n in p.names)           # one entry from each person: they were compared
st.title(f"Survey {code}")
st.write(f"Entered by **{info['entered_by']}** · ⚠ {info['differences']} differences · status: **{info['status']}**")

saved = info["start"] if info["start"] in available else None
start = st.radio("Start from the entry closest to the paper:", available, available.index(saved) if saved else 0,
                 horizontal=True, key=f"start|{code}")
if saved and start != saved:
    st.warning(f"This survey was being corrected from **{saved}**. If you save from **{start}**, the survey "
               f"will be exported from {start} (your changes to {saved} are kept in the log, not used).")

by_system, by_wj = info["differences"] > 0, bool(p.wj.get(code))
flagged = {(True, True): f"the **system** ({A} and {B} disagree) **and {TEAM}**",
           (True, False): f"the **system** only ({A} and {B} disagree)",
           (False, True): f"**{TEAM}** only",
           (False, False): f"nobody: {A} and {B} agree and there is no {TEAM} decision" if compared
           else f"nobody, but {A} and {B} were **not compared** (this code doesn't have exactly one entry from each)"}[by_system, by_wj]
st.info(f"**Flagged by:** {flagged}")
related = p.related_entries(code)
counts = ", ".join(f"{w} ×{n}" for w, n in related["Entered by"].value_counts().items())
several = related["Survey code"].nunique() > 1 or (related["In the tool"] != "used").any()
(st.warning if several else st.success)(
    f"**Entries with this survey number ({len(related)}):** {counts}"
    + (": more than one paper may share this number, or an entry is set aside. "
       "Make sure the entry you start from matches the paper you're correcting." if several else ""))
st.table(related.set_index("Survey code"))
with st.expander("Another paper with this same code? Give it its own code"):
    new_code = st.text_input("New code for the other paper", placeholder=f"e.g. {code}-2")
    if st.button("Add survey with this code") and new_code.strip():
        try:
            p.add_code(new_code, code)
        except ValueError as e:
            st.error(str(e))
        else:
            st.session_state["go_to"] = new_code.strip()
            st.rerun()
if by_system:
    st.error(f"⚠ **System: {info['differences']} answer(s) where {A} and {B} disagree**: check these on the paper")
    st.table(p.difference_notes(code).set_index("Question"))
if by_wj:
    st.warning(f"⚑ **{TEAM} decisions for this survey ({len(p.wj[code])})**: apply these when correcting")
    st.table(pd.DataFrame(p.wj[code]).rename(columns={
        "tag": "Question", "question": "Issue noted", "rule": "Decision", "notes": "Notes"}).set_index("Question"))

current = p.record(code, start)
new = {}
with st.form(f"{code}|{start}"):
    for q, cols in p.questions():
        st.markdown(f"#### {q['tag']}. {q['text']}")
        for hint in [h for h in p.wj.get(code, []) if h["tag"] == q["tag"]]:
            st.warning(f"⚑ {TEAM}: {hint['question']} → **{hint['rule']}** {hint['notes']}")
        for c in cols:
            col, key = c["column"], f"{code}|{start}|{c['column']}"
            options = p.options(col)
            option = {**q.get("choices", {}), **q.get("rows", {})}.get(c["choice"], "")
            if c["is_text"]:
                new[col] = st.text_input(f"{option} (text)" if option else "Answer", current[col], key=key)
            elif q["kind"] == "check_all":
                new[col] = "1" if st.checkbox(option, current[col] == "1", key=key) else ""
            else:
                labels_ = {"": "(blank)", **q.get("scale" if q["kind"] == "grid" else "choices", {})}
                index = options.index(current[col]) if current[col] in options else 0
                new[col] = st.radio(option or "Answer", options, index, key=key, horizontal=True,
                                    format_func=lambda v, l=labels_: l.get(v, v))
            values = {s: p.value(s, code, col) for s in available}   # every entry, side by side
            line = "  |  ".join(f"{s}: {p.label(col, v)}" for s, v in values.items())
            differ = p.disagree(code, col) if compared else len(set(values.values())) > 1
            st.markdown(f":red[**⚠ {line}**]" if differ else f":gray[{line}]")
    saved = st.form_submit_button("Save changes", type="primary")

if saved:
    n = p.save(code, start, new)
    st.success(f"Saved {n} change(s).")
    st.rerun()

done = st.button("Mark survey done ✓") if info["status"] != "done" else st.button("Reopen survey")
if done:
    p.set_status(code, start, "done" if info["status"] != "done" else "in progress")
    st.rerun()
