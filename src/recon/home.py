"""Home screen of the tool: open a survey project, or set up a new one step by step."""

import re
from pathlib import Path

import pandas as pd
import streamlit as st

from recon import setup


def page():
    if "setting_up" in st.session_state:
        return settings(Path(st.session_state["setting_up"]))
    st.title("Survey corrections")
    st.write("Each paper survey is typed in twice, by two people. This tool shows where the two entries "
             "disagree, lets you correct each survey against the paper, and exports the corrected data "
             "for Qualtrics.")

    st.subheader("Your projects")
    found = setup.projects()
    if not found:
        st.info("No projects yet: set up your first one below.")
    for root in found:
        name, ready = setup.draft(root).get("survey_name", root.name), setup.is_ready(root)
        left, right = st.columns([4, 1])
        left.markdown(f"**{name}**  \n" + (f"{setup.done_count(root)} surveys done" if ready else "Setup not finished"))
        if right.button("Open" if ready else "Continue setup", key=f"open|{root}", use_container_width=True):
            st.session_state["project" if ready else "setting_up"] = str(root)
            st.rerun()

    st.subheader("Set up a new survey")
    with st.form("new"):
        name = st.text_input("Project name", placeholder="e.g. Spring 2027 housing survey")
        qsf = st.file_uploader("Survey file (.qsf). In Qualtrics: open the survey → Tools → Import/Export → "
                               "Export Survey", type="qsf")
        main = st.file_uploader("Responses (.csv). In Qualtrics: Data & Analysis → Export & Import → Export Data "
                                "→ CSV, with **Use numeric values** selected", type="csv")
        extras = st.file_uploader("Other responses files of the same survey (optional), e.g. a copy of the survey "
                                  "that one person typed into", type="csv", accept_multiple_files=True)
        if st.form_submit_button("Create project", type="primary"):
            if not (qsf and main):
                st.error("Add the survey file and the responses file.")
                return
            try:
                root = setup.create(name, (qsf.name, qsf.getvalue()), (main.name, main.getvalue()),
                                    [(f.name, f.getvalue()) for f in extras])
            except ValueError as e:
                st.error(str(e))
            else:
                st.session_state["setting_up"] = str(root)
                st.rerun()


def settings(root: Path):
    """Choose the settings for a new project, then prepare it."""
    if st.button("← All projects"):
        st.session_state.pop("setting_up")
        st.session_state.pop("summary", None)
        st.rerun()
    st.title(f"Set up: {setup.draft(root)['survey_name']}")

    if "summary" in st.session_state:
        st.success("The project is ready to correct.")
        st.table(pd.DataFrame(st.session_state["summary"], columns=["What", "Count"]).set_index("What"))
        if st.button("Open project", type="primary"):
            st.session_state["project"] = st.session_state.pop("setting_up")
            st.session_state.pop("summary")
            st.rerun()
        return

    st.subheader("1. Which question holds the survey code?")
    st.caption("The question where each person typed the code from the paper followed by their initials, "
               "e.g. 1-0235 HS. The likeliest one is chosen for you.")
    questions = setup.code_questions(root)
    if not questions:
        st.error("This survey has no text-entry question to hold the survey code.")
        return
    q = st.selectbox("Survey code question", questions, format_func=lambda q: f"{q['text'][:80]}  (e.g. {q['example']})")
    id_column = q["column"]

    st.subheader("2. Who typed the surveys in?")
    found = setup.initials(root, id_column)
    if len(found) < 2:
        st.error("Fewer than two people's initials were found at the end of the codes. Is it the right question?")
        return
    st.caption("Initials found at the end of the codes: "
               + ", ".join(f"**{i}** ({n} entries)" for i, n in found.most_common()))
    people = st.multiselect("The two people", list(found), [i for i, _ in found.most_common(2)], max_selections=2)

    st.subheader("3. What does a correct survey code look like?")
    codes = setup.codes(root, id_column)
    example = st.text_input("One correct code, as written on the paper (without initials)",
                            setup.typical_code(codes), key=f"example|{id_column}")
    if example.strip():
        pattern = re.compile(setup.pattern_from_example(example))
        odd = sorted({c for c in codes if not pattern.match(c)})
        st.caption(f"{len(codes) - sum(not pattern.match(c) for c in codes)} of {len(codes)} typed codes look like "
                   "this." + (f" The rest are kept but marked as unusual, e.g. {', '.join(odd[:8])}." if odd else ""))

    st.subheader("4. Extras (optional)")
    logs = {}
    with st.expander("Paper logs: a list of the survey numbers each person typed"):
        st.caption("A text file with one survey number per line (or separated by spaces). Entries missing from "
                   "the log, or on it twice, are set aside so you can check them.")
        for person in people:
            if f := st.file_uploader(f"Paper log for {person}", type="txt", key=f"log|{person}"):
                logs[person] = (f.name, f.getvalue())
    decisions = None
    with st.expander("Decisions sheet: decisions made about specific surveys, shown while correcting"):
        if f := st.file_uploader("Spreadsheet (.xlsx)", type="xlsx"):
            xl = pd.ExcelFile(f)
            sheet = st.selectbox("Sheet", xl.sheet_names)
            cols = [str(c) for c in pd.read_excel(xl, sheet_name=sheet, nrows=0).columns]
            decisions = {
                "sheet": sheet,
                "label": st.text_input("Who made the decisions (shown in the tool)", "Team"),
                "survey_columns": st.multiselect("Column(s) that identify the survey, e.g. location and number", cols),
                "question_column": st.selectbox("Column with the question or issue", cols),
                "decision_column": st.selectbox("Column with the decision", cols),
                "notes_column": st.selectbox("Column with notes", [None, *cols], format_func=lambda c: c or "(none)"),
                "upload": (f.name, f.getvalue())}
            if not decisions["survey_columns"]:
                st.warning("Choose the column(s) that identify the survey, or the decisions can't be matched.")

    if st.button("Prepare project", type="primary"):
        with st.spinner("Reading the responses and comparing the two people's entries…"):
            try:
                st.session_state["summary"] = setup.prepare(root, id_column, people, example, logs, decisions)
            except ValueError as e:
                st.error(str(e))
            else:
                st.rerun()
