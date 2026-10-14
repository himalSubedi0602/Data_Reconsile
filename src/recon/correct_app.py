"""The correction screen. Run from the project root:

    .venv/bin/streamlit run src/recon/correct_app.py
"""

from datetime import date

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
    find = st.text_input("Find a survey code (searches all surveys)", placeholder="e.g. 1436 or 3-2621")
    if find.strip():
        shown = surveys[surveys["survey_code"].str.contains(find.strip(), regex=False)]
    else:
        shown = surveys[FILTERS[st.selectbox("Show", list(FILTERS))]]
    st.caption(f"{len(shown)} surveys · {(shown['status'] == 'done').sum()} done")
    if shown.empty:
        st.info("No survey matches." if find.strip() else "No surveys in this list.")
        st.stop()
    labels = {r.survey_code: f"{r.survey_code}  ·  {r.entered_by}  ·  ⚠ {r.differences}"
              + (f"  ⚑ {r.wj}" if r.wj else "") + f"  ·  {r.status}" for r in shown.itertuples()}
    codes = list(labels)
    if st.session_state.get("survey") not in codes:
        st.session_state["survey"] = codes[0]
    if st.button("Next survey →", use_container_width=True):
        st.session_state["survey"] = codes[(codes.index(st.session_state["survey"]) + 1) % len(codes)]
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
available = [n for n in p.names if n in info["entered_by"]]
st.title(f"Survey {code}")
st.write(f"Entered by **{info['entered_by']}** · ⚠ {info['differences']} differences · status: **{info['status']}**")

if info["start"]:
    start = info["start"]
    st.write(f"Correcting the **{start}** entry.")
else:
    start = st.radio("Start from the entry closest to the paper:", available, horizontal=True)

for hint in [h for h in p.wj.get(code, []) if not h["tag"]]:
    st.warning(f"⚑ W&J: {hint['question']} → {hint['rule']} {hint['notes']}")

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
            hs, ch = (p.label(col, p.value(n, code, col)) for n in p.names)
            line = f"{p.names[0]}: {hs}  |  {p.names[1]}: {ch}"
            st.markdown(f":red[**⚠ {line}**]" if p.disagree(code, col) else f":gray[{line}]")
    saved = st.form_submit_button("Save changes", type="primary")

if saved:
    n = p.save(code, start, new)
    st.success(f"Saved {n} change(s).")
    st.rerun()

done = st.button("Mark survey done ✓") if info["status"] != "done" else st.button("Reopen survey")
if done:
    p.set_status(code, start, "done" if info["status"] != "done" else "in progress")
    st.rerun()
