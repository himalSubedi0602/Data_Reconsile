"""The correction screen. Run from the project root:

    .venv/bin/streamlit run src/recon/correct_app.py
"""

import re
from datetime import date

import pandas as pd
import streamlit as st

from recon.corrections import STATUSES, Project

st.set_page_config(page_title="Survey corrections", layout="wide")


@st.cache_resource
def project() -> Project:
    return Project()


p = project()
surveys = p.surveys()

# ------------------------------------------------------------ left: find a survey
FILTERS = {
    "Flagged (HS and CH disagree)": surveys["differences"] > 0,
    "W&J decision": surveys["wj"] > 0,
    "Not started": surveys["status"] == "not started",
    "In progress": surveys["status"] == "in progress",
    "Done": surveys["status"] == "done",
    "All surveys": surveys["survey_code"] != "",
}
with st.sidebar:
    st.header("Surveys")
    shown = surveys[FILTERS[st.selectbox("Show", list(FILTERS), index=list(FILTERS).index("All surveys"))]]
    # Survey number = the 4 digits after the location: 1-0235 -> 235 (typo codes: "All numbers" only).
    number = surveys["survey_code"].map(lambda c: int(m.group(1)) if (m := re.match(r"\d+-(\d{4})(?!\d)", c)) else -1)
    ranges = {"All numbers": (-1, 10**9)} | {
        f"{0 if i == 0 else i * 200 + 1}–{(i + 1) * 200}": (0 if i == 0 else i * 200 + 1, (i + 1) * 200)
        for i in range(number.max() // 200 + 1)}
    low, high = ranges[st.selectbox("Survey numbers", list(ranges))]
    shown = shown[number[shown.index].between(low, high)]
    find = st.text_input("Find a survey code (within the list above)", placeholder="e.g. 1436 or 3-2621")
    if find.strip():
        shown = shown[shown["survey_code"].str.contains(find.strip(), regex=False)]
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

    st.divider()
    st.subheader("Results")
    done, open_ = (surveys["status"] == "done").sum(), (surveys["status"] == "in progress").sum()
    st.caption(f"{done} surveys done · {open_} in progress (not exported until marked done)")
    name = st.text_input("Name for the files", f"round1_{date.today()}")
    if st.button("Export corrected CSV (done surveys)", use_container_width=True):
        n = p.export(p.store / f"corrected_{name}.csv")
        st.success(f"Wrote {n} surveys to data/corrections/corrected_{name}.csv")
    if st.button("Make random check sheet (10 surveys)", use_container_width=True):
        picked = p.random_check(p.store / f"random_check_{name}.xlsx")
        st.success(f"Picked {', '.join(picked)} → data/corrections/random_check_{name}.xlsx")

# ------------------------------------------------------------ right: the survey
info = surveys.set_index("survey_code").loc[code]
available = list(p.starts[code])                         # every HS/CH entry with this code, used or set aside
compared = sorted(available) == sorted(p.names)           # exactly one entry each: HS and CH were compared
st.title(f"Survey {code}")
st.write(f"Entered by **{info['entered_by']}** · ⚠ {info['differences']} differences · status: **{info['status']}**")

if info["start"]:
    start = info["start"]
    st.write(f"Correcting the **{start}** entry.")
else:
    start = st.radio("Start from the entry closest to the paper:", available, horizontal=True)

by_system, by_wj = info["differences"] > 0, bool(p.wj.get(code))
flagged = {(True, True): "the **system** (HS and CH disagree) **and W&J**", (True, False): "the **system** only (HS and CH disagree)",
           (False, True): "**W&J** only",
           (False, False): "nobody: HS and CH agree and there is no W&J decision" if compared
           else "nobody, but HS and CH were **not compared** (this code doesn't have exactly one entry from each)"}[by_system, by_wj]
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
    st.error(f"⚠ **System: {info['differences']} answer(s) where HS and CH disagree**: check these on the paper")
    st.table(p.difference_notes(code).set_index("Question"))
if by_wj:
    st.warning(f"⚑ **W&J decisions for this survey ({len(p.wj[code])})**: apply these when correcting")
    st.table(pd.DataFrame(p.wj[code]).rename(columns={
        "tag": "Question", "question": "Issue noted", "rule": "Decision", "notes": "Notes"}).set_index("Question"))

current = p.record(code, start)
new = {}
with st.form(f"{code}|{start}"):
    for q, cols in p.questions():
        st.markdown(f"#### {q['tag']}. {q['text']}")
        for hint in [h for h in p.wj.get(code, []) if h["tag"] == q["tag"]]:
            st.warning(f"⚑ W&J: {hint['question']} → **{hint['rule']}** {hint['notes']}")
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
