"""
Course Flowchart Visualizer - Streamlit Application

This application visualizes degree program course flowcharts, showing course
prerequisites and progression through semesters. It includes critical path
analysis and a course editor.
"""

import streamlit as st
import graphviz
import json
import os
import re
from pathlib import Path
from typing import Optional
import pandas as pd

# Page configuration
st.set_page_config(
    page_title="Course Flowchart",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for OSU orange theme
# Official OSU Orange: #FE5C00 (per brand.okstate.edu)
st.markdown("""
<style>
    /* Primary button - Official OSU Orange */
    .stButton > button[kind="primary"] {
        background-color: #FE5C00;
        border-color: #FE5C00;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #E55300;
        border-color: #E55300;
    }
    .stButton > button[kind="primary"]:active {
        background-color: #CC4A00;
        border-color: #CC4A00;
    }

</style>
""", unsafe_allow_html=True)


def natural_sort_key(text: str):
    """Generate a sort key that handles embedded numbers naturally.

    E.g., "CHEM 4000" sorts before "CHEM 4523" instead of after.
    """
    parts = re.split(r'(\d+)', text)
    return [int(part) if part.isdigit() else part.lower() for part in parts]


def load_program_data(file_path: str) -> dict:
    """Load program data from a JSON file."""
    with open(file_path, 'r') as f:
        return json.load(f)


def get_available_programs() -> list[dict]:
    """Find all JSON program files in the current directory.

    Returns a list of dicts with program metadata including:
    - filename: the JSON file path
    - institution: institution name
    - college: college name
    - department: department name
    - major: program/major name
    """
    programs = []
    # Find all JSON files in the data directory
    for filename in Path("data").glob("*.json"):
        filename_str = str(filename)
        # Skip hidden files and non-program files
        if filename_str.startswith("."):
            continue
        try:
            data = load_program_data(filename_str)
            # Verify it looks like a program file (has required fields)
            if "major" in data and "courses" in data:
                programs.append({
                    "filename": filename_str,
                    "institution": data.get("institution", "Unknown Institution"),
                    "college": data.get("college", ""),
                    "department": data.get("department", "Unknown Department"),
                    "major": data.get("major", filename_str)
                })
        except (json.JSONDecodeError, KeyError):
            continue
    return programs


def calculate_critical_path(courses: list[dict]) -> dict:
    """
    Calculate critical path metrics for all courses.

    Returns a dict with course_id -> {depth, height, earliest_semester, is_critical}
    """
    course_map = {c["id"]: c for c in courses}
    metrics = {}

    # Calculate depth (longest chain of prerequisites to reach this course)
    def calc_depth(course_id: str, visited: set = None) -> int:
        if visited is None:
            visited = set()
        if course_id in visited:
            return 0
        visited.add(course_id)

        course = course_map.get(course_id)
        if not course or not course.get("prerequisites"):
            return 0

        max_prereq_depth = 0
        for prereq_id in course["prerequisites"]:
            if prereq_id in course_map:
                prereq_depth = calc_depth(prereq_id, visited.copy())
                max_prereq_depth = max(max_prereq_depth, prereq_depth + 1)

        return max_prereq_depth

    # Calculate height (longest chain of courses dependent on this one)
    def calc_height(course_id: str, visited: set = None) -> int:
        if visited is None:
            visited = set()
        if course_id in visited:
            return 0
        visited.add(course_id)

        max_dep_height = 0
        for c in courses:
            if course_id in c.get("prerequisites", []):
                dep_height = calc_height(c["id"], visited.copy())
                max_dep_height = max(max_dep_height, dep_height + 1)

        return max_dep_height

    # Calculate metrics for each course
    for course in courses:
        course_id = course["id"]
        depth = calc_depth(course_id)
        height = calc_height(course_id)
        earliest_semester = depth + 1  # 1-indexed

        metrics[course_id] = {
            "depth": depth,
            "height": height,
            "earliest_semester": earliest_semester,
            "path_length": depth + height
        }

    # Find critical path length (maximum path_length)
    if metrics:
        critical_length = max(m["path_length"] for m in metrics.values())

        # Mark courses on critical path
        for course_id, m in metrics.items():
            m["is_critical"] = (m["path_length"] == critical_length)

    return metrics


def get_semester_color(semester: int, max_semester: int = 8) -> str:
    """Generate a color for a semester (light to dark orange gradient)."""
    # Orange gradient from light to dark
    colors = [
        "#FFF4E6",  # Semester 1 - lightest
        "#FFE4CC",  # Semester 2
        "#FFD4B3",  # Semester 3
        "#FFC499",  # Semester 4
        "#FFB480",  # Semester 5
        "#FFA366",  # Semester 6
        "#FF934D",  # Semester 7
        "#FF8333",  # Semester 8 - darkest
    ]
    idx = min(semester - 1, len(colors) - 1)
    return colors[max(0, idx)]


def get_contrast_text_color(hex_color: str) -> str:
    """Return black or white text color based on background luminance."""
    # Remove # prefix
    hex_color = hex_color.lstrip('#')

    # Convert to RGB
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)

    # Calculate relative luminance (ITU-R BT.709)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255

    # Return black for light backgrounds, white for dark
    return "#000000" if luminance > 0.5 else "#FFFFFF"


def create_flowchart(
    program_data: dict,
    metrics: dict,
    selected_course: Optional[str] = None,
    show_critical_path: bool = False
) -> graphviz.Digraph:
    """Create a Graphviz flowchart for the program."""

    dot = graphviz.Digraph(
        comment=program_data["major"],
        format='svg'
    )

    # Graph attributes for top-to-bottom layout
    dot.attr(
        rankdir='TB',
        splines='ortho',
        nodesep='0.5',
        ranksep='0.8',
        bgcolor='#0e1117',  # Match Streamlit dark mode background
        newrank='true'  # Enable new ranking algorithm for better control
    )

    # Default node attributes
    dot.attr('node',
        shape='box',
        style='filled,rounded',
        fontname='Arial',
        fontsize='11',
        margin='0.15,0.1'
    )

    # Default edge attributes
    dot.attr('edge',
        color='#9CA3AF',  # Lighter gray for dark background
        arrowsize='0.7'
    )

    courses = program_data["courses"]
    course_map = {c["id"]: c for c in courses}

    # Group courses by semester
    semesters = {}
    for course in courses:
        sem = course["semester"]
        if sem not in semesters:
            semesters[sem] = []
        semesters[sem].append(course)

    sorted_semesters = sorted(semesters.keys())

    # Create semester label nodes and invisible edges to enforce row ordering
    for i, sem in enumerate(sorted_semesters):
        # Create semester label node
        sem_label_id = f"sem_label_{sem}"
        dot.node(
            sem_label_id,
            label=f"Semester {sem}",
            shape='plaintext',
            fontname='Arial Bold',
            fontsize='12',
            fontcolor='#9CA3AF'  # Lighter gray for dark background
        )

        # Create invisible edge to next semester to enforce ordering
        if i < len(sorted_semesters) - 1:
            next_sem = sorted_semesters[i + 1]
            next_sem_label_id = f"sem_label_{next_sem}"
            dot.edge(sem_label_id, next_sem_label_id, style='invis')

    # Create subgraphs for each semester to enforce ranking
    for sem in sorted_semesters:
        with dot.subgraph() as s:
            s.attr(rank='same')

            # Include semester label in this rank
            sem_label_id = f"sem_label_{sem}"
            s.node(sem_label_id)

            for course in semesters[sem]:
                course_id = course["id"]
                course_metrics = metrics.get(course_id, {})
                is_critical = course_metrics.get("is_critical", False)

                # Determine node styling
                bg_color = get_semester_color(sem)
                border_color = "#6B7280"  # Medium gray for dark background
                font_color = "#333333"
                penwidth = "1"

                # Highlight selected course
                if selected_course and course_id == selected_course:
                    border_color = "#FE5C00"  # OSU Orange
                    penwidth = "3"

                # Dim non-critical courses if critical path is shown
                if show_critical_path and not is_critical:
                    bg_color = "#374151"  # Dark gray for dark background
                    font_color = "#9CA3AF"  # Light gray text
                    border_color = "#4B5563"
                elif show_critical_path and is_critical:
                    border_color = "#EF4444"  # Red for critical path
                    penwidth = "2"

                # Create label with course info
                label = f"{course_id}\\n{course['name']}\\n({course['credits']} cr)"

                s.node(
                    course_id,
                    label=label,
                    fillcolor=bg_color,
                    color=border_color,
                    fontcolor=font_color,
                    penwidth=penwidth
                )

    # Add edges for prerequisites
    for course in courses:
        course_id = course["id"]
        for prereq_id in course.get("prerequisites", []):
            if prereq_id in course_map:
                edge_color = "#9CA3AF"  # Lighter gray for dark background
                penwidth = "1"

                # Highlight edges connected to selected course
                if selected_course and (course_id == selected_course or prereq_id == selected_course):
                    edge_color = "#FE5C00"  # OSU Orange
                    penwidth = "2"

                # Highlight critical path edges
                if show_critical_path:
                    prereq_critical = metrics.get(prereq_id, {}).get("is_critical", False)
                    course_critical = metrics.get(course_id, {}).get("is_critical", False)
                    if prereq_critical and course_critical:
                        edge_color = "#EF4444"  # Red for critical path
                        penwidth = "2"
                    elif not prereq_critical or not course_critical:
                        edge_color = "#4B5563"  # Dimmed gray for dark background

                dot.edge(prereq_id, course_id, color=edge_color, penwidth=penwidth)

    return dot


def display_course_details(course: dict, metrics: dict, all_courses: list[dict]):
    """Display detailed information about a selected course."""
    course_id = course["id"]
    course_metrics = metrics.get(course_id, {})
    course_map = {c["id"]: c for c in all_courses}

    st.subheader(f"📖 {course_id}")
    st.markdown(f"**{course['name']}**")

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Credits", course["credits"])
    with col2:
        st.metric("Semester", course["semester"])

    if course.get("offering"):
        st.markdown(f"**Offering:** {course['offering']}")

    st.markdown("---")
    st.markdown(f"**Description:**\n\n{course.get('description', 'No description available.')}")

    # Prerequisites
    prereqs = course.get("prerequisites", [])
    if prereqs:
        st.markdown("---")
        st.markdown("**Prerequisites:**")
        for prereq_id in prereqs:
            prereq = course_map.get(prereq_id)
            if prereq:
                st.markdown(f"- {prereq_id}: {prereq['name']}")
            else:
                st.markdown(f"- {prereq_id}")

    # Path metrics
    st.markdown("---")
    st.markdown("**Path Metrics:**")

    earliest = course_metrics.get("earliest_semester", 1)
    depth = course_metrics.get("depth", 0)
    height = course_metrics.get("height", 0)
    is_critical = course_metrics.get("is_critical", False)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Earliest Semester", earliest)
    with col2:
        st.metric("Prereq Chain", depth)
    with col3:
        st.metric("Dependents Chain", height)

    if earliest != course["semester"]:
        st.warning(f"This course could be taken as early as semester {earliest}, but is scheduled for semester {course['semester']}.")

    if is_critical:
        st.error("⚠️ This course is on the CRITICAL PATH. Delaying it will extend graduation time.")


def flowchart_viewer_page():
    """Flowchart viewer page."""

    # Header
    st.title("📚 Course Flowchart Visualizer")
    st.markdown("Interactive visualization of degree program course progression and prerequisites.")

    # Load available programs
    programs = get_available_programs()

    if not programs:
        st.error("No program data files found. Please ensure JSON files are in the application directory.")
        return

    # Build hierarchical structure for cascading dropdowns
    institutions = sorted(set(p["institution"] for p in programs))

    # Controls section at the top of the page
    with st.expander("Degree Program Selection", expanded=True):
        # Cascading dropdowns for program selection
        sel_col1, sel_col2, sel_col3 = st.columns(3)

        with sel_col1:
            selected_institution = st.selectbox(
                "Institution",
                options=institutions,
                index=0
            )

        # Filter departments by selected institution
        departments_for_institution = sorted(set(
            p["department"] for p in programs
            if p["institution"] == selected_institution
        ))

        with sel_col2:
            selected_department = st.selectbox(
                "Department",
                options=departments_for_institution,
                index=0
            )

        # Filter programs by selected institution and department
        programs_for_dept = [
            p for p in programs
            if p["institution"] == selected_institution
            and p["department"] == selected_department
        ]
        program_names = [p["major"] for p in programs_for_dept]

        with sel_col3:
            selected_major = st.selectbox(
                "Degree Program",
                options=program_names,
                index=0
            )

    # Find the selected program's filename
    selected_program_data = next(
        (p for p in programs_for_dept if p["major"] == selected_major),
        programs_for_dept[0] if programs_for_dept else None
    )

    if not selected_program_data:
        st.error("No program selected.")
        return

    # Load program data
    program_data = load_program_data(selected_program_data["filename"])
    courses = program_data["courses"]
    course_map = {c["id"]: c for c in courses}

    # Calculate metrics
    metrics = calculate_critical_path(courses)

    # Program info header
    institution = program_data.get("institution", "")
    college = program_data.get("college", "")
    department = program_data.get("department", "")

    if institution:
        st.markdown(f"**{institution}**")
    if college or department:
        org_parts = [p for p in [college, department] if p]
        st.markdown(f"*{' | '.join(org_parts)}*")
    st.markdown(f"### {program_data['major']}")
    st.markdown(program_data.get("description", ""))

    # Program stats
    stat_col1, stat_col2, stat_col3 = st.columns(3)
    with stat_col1:
        st.metric("Total Credits", program_data.get('totalCredits', 'N/A'))
    with stat_col2:
        st.metric("Total Courses", len(courses))
    with stat_col3:
        if metrics:
            critical_length = max(m["path_length"] for m in metrics.values()) + 1
            st.metric("Critical Path Length", f"{critical_length} semesters")

    st.markdown("---")

    # Flowchart controls section
    st.markdown("#### Course Flowchart")

    ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns([2, 1, 1, 1])

    with ctrl_col1:
        # Course selection
        course_options = ["None"] + [f"{c['id']} - {c['name']}" for c in sorted(courses, key=lambda x: natural_sort_key(x['id']))]
        selected_course_str = st.selectbox(
            "Select Course for Details",
            options=course_options,
            index=0
        )

    with ctrl_col2:
        st.markdown("")  # Spacing to align with selectbox
        show_critical = st.checkbox("Highlight Critical Path", value=False)

    with ctrl_col3:
        st.markdown("")  # Spacing to align with selectbox
        show_legend = st.checkbox("Show Legend", value=False)

    with ctrl_col4:
        pass  # Empty column for spacing

    selected_course_id = None
    if selected_course_str != "None":
        selected_course_id = selected_course_str.split(" - ")[0]

    # Legend
    if show_legend:
        legend_cols = st.columns(8)
        for i, col in enumerate(legend_cols):
            sem = i + 1
            bg_color = get_semester_color(sem)
            text_color = get_contrast_text_color(bg_color)
            col.markdown(
                f'<div style="background-color: {bg_color}; color: {text_color}; '
                f'padding: 0.3125rem; text-align: center; border-radius: 0.25rem; font-size: 0.75rem;">'
                f'Sem {sem}</div>',
                unsafe_allow_html=True
            )
        st.markdown("")

    # Main content area - flowchart and details
    if selected_course_id and selected_course_id in course_map:
        col1, col2 = st.columns([3, 1])
    else:
        col1, col2 = st.columns([1, 0.001])

    with col1:
        # Create and display flowchart
        flowchart = create_flowchart(
            program_data,
            metrics,
            selected_course=selected_course_id,
            show_critical_path=show_critical
        )

        st.graphviz_chart(flowchart, width="stretch")

    # Course details panel
    if selected_course_id and selected_course_id in course_map:
        with col2:
            display_course_details(
                course_map[selected_course_id],
                metrics,
                courses
            )


def editor_page():
    """Course editor page."""
    st.title("📝 Course Editor")
    st.markdown("Create and edit degree program course data.")

    # Initialize session state for editor
    if "editor_data" not in st.session_state:
        st.session_state.editor_data = {
            "institution": "",
            "college": "",
            "department": "",
            "major": "New Degree Program",
            "totalCredits": 120,
            "description": "Degree program description here.",
            "courses": []
        }

    # Load/Import section at the top
    with st.expander("Load or Import Degree Program", expanded=True):
        load_col1, load_col2 = st.columns(2)

        with load_col1:
            st.markdown("**Load Existing Degree Program**")
            programs = get_available_programs()
            if programs:
                # Create display labels with institution/department context
                program_options = ["-- New Degree Program --"] + [
                    f"{p['major']} ({p['institution']} - {p['department']})"
                    for p in programs
                ]

                load_program_idx = st.selectbox(
                    "Select program",
                    options=range(len(program_options)),
                    format_func=lambda i: program_options[i],
                    label_visibility="collapsed"
                )

                if st.button("Load Degree Program"):
                    if load_program_idx == 0:  # "-- New Degree Program --"
                        # Reset to blank template
                        st.session_state.editor_data = {
                            "institution": "",
                            "college": "",
                            "department": "",
                            "major": "New Degree Program",
                            "totalCredits": 120,
                            "description": "Degree program description here.",
                            "courses": []
                        }
                        # Clear any exported JSON
                        if "export_json" in st.session_state:
                            del st.session_state.export_json
                        if "filename_input" in st.session_state:
                            del st.session_state.filename_input
                        st.rerun()
                    else:
                        # Load selected program (index - 1 because of "-- New Degree Program --")
                        selected_program = programs[load_program_idx - 1]
                        st.session_state.editor_data = load_program_data(selected_program["filename"])
                        # Set filename to existing filename (without path and .json extension)
                        existing_filename = Path(selected_program["filename"]).stem
                        st.session_state.filename_input = existing_filename
                        # Clear any exported JSON preview
                        if "export_json" in st.session_state:
                            del st.session_state.export_json
                        st.rerun()

        with load_col2:
            st.markdown("**Import JSON File**")
            uploaded_file = st.file_uploader("Upload JSON file", type=['json'], label_visibility="collapsed", key="json_uploader")
            if uploaded_file:
                # Check if we've already processed this file to avoid infinite rerun loop
                file_id = f"{uploaded_file.name}_{uploaded_file.size}"
                if st.session_state.get("last_uploaded_file") != file_id:
                    try:
                        data = json.load(uploaded_file)
                        st.session_state.editor_data = data
                        st.session_state.last_uploaded_file = file_id
                        st.success("Data loaded successfully!")
                        st.rerun()
                    except json.JSONDecodeError:
                        st.error("Invalid JSON file")

    # Main editor area
    data = st.session_state.editor_data

    # Degree program info
    st.subheader("Degree Program Information")

    data["institution"] = st.text_input("Institution", value=data.get("institution", ""))

    col1, col2 = st.columns(2)
    with col1:
        data["college"] = st.text_input("College", value=data.get("college", ""))
    with col2:
        data["department"] = st.text_input("Department", value=data.get("department", ""))

    col1, col2 = st.columns(2)
    with col1:
        data["major"] = st.text_input("Degree Program Name", value=data["major"])
    with col2:
        data["totalCredits"] = st.number_input("Total Credits", value=data["totalCredits"], min_value=0)

    data["description"] = st.text_area("Description", value=data["description"])

    st.markdown("---")

    # Course table
    st.subheader("Courses")

    if data["courses"]:
        # Create DataFrame for editing
        course_df = pd.DataFrame(data["courses"])

        # Convert prerequisites list to string for display
        if "prerequisites" in course_df.columns:
            course_df["prerequisites"] = course_df["prerequisites"].apply(
                lambda x: ", ".join(x) if isinstance(x, list) else ""
            )

        # Use data editor
        edited_df = st.data_editor(
            course_df,
            num_rows="dynamic",
            width="stretch",
            column_config={
                "id": st.column_config.TextColumn("Course ID", required=True),
                "name": st.column_config.TextColumn("Course Name", required=True),
                "credits": st.column_config.NumberColumn("Credits", min_value=0, max_value=10, required=True),
                "semester": st.column_config.NumberColumn("Semester", min_value=1, max_value=12, required=True),
                "description": st.column_config.TextColumn("Description", width="large"),
                "prerequisites": st.column_config.TextColumn("Prerequisites (comma-separated IDs)")
            }
        )

        # Convert back to list format
        if st.button("Apply Changes"):
            courses = edited_df.to_dict('records')
            for course in courses:
                prereqs = course.get("prerequisites", "")
                if isinstance(prereqs, str):
                    course["prerequisites"] = [p.strip() for p in prereqs.split(",") if p.strip()]
            data["courses"] = courses
            st.success("Changes applied!")
    else:
        st.info("No courses yet. Add courses below.")

    # Add new course
    st.markdown("---")
    st.subheader("Add New Course")

    with st.form("new_course_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            new_id = st.text_input("Course ID", placeholder="e.g., CHEM 1314")
        with col2:
            new_name = st.text_input("Course Name", placeholder="e.g., General Chemistry I")
        with col3:
            new_credits = st.number_input("Credits", value=3, min_value=0, max_value=10)

        col1, col2 = st.columns(2)
        with col1:
            new_semester = st.number_input("Semester", value=1, min_value=1, max_value=12)
        with col2:
            existing_ids = [c["id"] for c in data["courses"]]
            new_prereqs = st.multiselect("Prerequisites", options=existing_ids)

        new_desc = st.text_area("Description")

        if st.form_submit_button("Add Course"):
            if new_id and new_name:
                new_course = {
                    "id": new_id,
                    "name": new_name,
                    "credits": new_credits,
                    "semester": new_semester,
                    "description": new_desc,
                    "prerequisites": new_prereqs
                }
                data["courses"].append(new_course)
                st.success(f"Added course: {new_id}")
                st.rerun()
            else:
                st.error("Course ID and Name are required")

    # Save/Export section
    st.markdown("---")
    st.subheader("Save & Export")

    # Generate default filename from program name
    default_filename = data['major'].lower().replace(' ', '-').replace(',', '').replace('(', '').replace(')', '')

    # Initialize filename in session state if not set
    if "filename_input" not in st.session_state:
        st.session_state.filename_input = default_filename

    # Filename input
    export_filename = st.text_input(
        "Filename (without .json extension)",
        key="filename_input"
    )

    final_filename = f"{export_filename}.json" if export_filename else "program-data.json"
    json_data = json.dumps(data, indent=2)

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Save to Server", type="primary"):
            try:
                save_path = f"data/{final_filename}"
                with open(save_path, 'w') as f:
                    f.write(json_data)
                st.success(f"Saved to {save_path}")
                # Clear cached programs so the new file shows up
                if "available_programs" in st.session_state:
                    del st.session_state.available_programs
            except Exception as e:
                st.error(f"Error saving file: {e}")

    with col2:
        st.download_button(
            "Download JSON",
            data=json_data,
            file_name=final_filename,
            mime="application/json"
        )

    with col3:
        if st.button("Preview JSON"):
            st.session_state.show_json_preview = not st.session_state.get("show_json_preview", False)

    if st.session_state.get("show_json_preview", False):
        st.code(json_data, language="json")


# Sidebar - Navigation only
with st.sidebar:
    st.title("📚 Course Flowchart")
    st.markdown("---")

    st.markdown("**Navigation**")

    # Get current page from query params
    query_params = st.query_params
    current_page = query_params.get("page", "viewer")

    # Navigation links styled as buttons
    viewer_type = "primary" if current_page == "viewer" else "secondary"
    editor_type = "primary" if current_page == "editor" else "secondary"

    if st.button("📊 Flowchart Viewer", type=viewer_type, use_container_width=True):
        st.query_params["page"] = "viewer"
        st.rerun()

    if st.button("📝 Course Editor", type=editor_type, use_container_width=True):
        st.query_params["page"] = "editor"
        st.rerun()

    st.markdown("---")
    st.markdown("*Select a page above to get started.*")

# Route to selected page based on query params
if current_page == "editor":
    editor_page()
else:
    flowchart_viewer_page()

# Footer
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #9CA3AF; font-size: 0.875rem;'>"
    "© 2025 All rights reserved."
    "</div>",
    unsafe_allow_html=True
)
