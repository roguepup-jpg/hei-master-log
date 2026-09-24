from datetime import datetime, date
import io
import os
import streamlit as st
import pandas as pd
import psycopg2
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas as pdf_canvas

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="HEI Master Engineering Control System",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- DATABASE CONNECTION ---
def get_db_connection():
    db_uri = st.secrets["connections"]["supabase"]["uri"]
    return psycopg2.connect(db_uri)

# --- INITIALIZE TABLES & AUTO-UPDATE SCHEMA ---
def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Create base table if it doesn't exist
        cur.execute("""
            CREATE TABLE IF NOT EXISTS esr_log (
                esr_number TEXT PRIMARY KEY
            );
        """)
        
        # Ensure all required columns exist (safe migration for existing tables)
        columns_to_add = [
            ("date_logged", "TEXT"),
            ("department", "TEXT"),
            ("priority_level", "TEXT"),
            ("originator", "TEXT"),
            ("project_system", "TEXT"),
            ("product_name", "TEXT"),
            ("service_title", "TEXT"),
            ("affected_assemblies", "TEXT"),
            ("problem_statement", "TEXT"),
            ("requested_deliverables", "TEXT"),
            ("operational_justification", "TEXT"),
            ("mechanical_impact", "TEXT"),
            ("electrical_impact", "TEXT"),
            ("qa_impact", "TEXT"),
            ("technical_risk", "TEXT"),
            ("mitigation_measures", "TEXT"),
            ("mech_signoff", "TEXT"),
            ("elec_signoff", "TEXT"),
            ("qa_signoff", "TEXT"),
            ("manager_signoff", "TEXT"),
            ("status", "TEXT")
        ]
        
        for col_name, col_type in columns_to_add:
            cur.execute(f"ALTER TABLE esr_log ADD COLUMN IF NOT EXISTS {col_name} {col_type};")

        # ESR Action Log Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS esr_action_log (
                action_id SERIAL PRIMARY KEY,
                esr_number TEXT,
                action_date TEXT,
                engineer TEXT,
                category TEXT,
                changed_drawings TEXT,
                notes TEXT,
                FOREIGN KEY (esr_number) REFERENCES esr_log (esr_number) ON DELETE CASCADE
            );
        """)
        
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        st.error(f"Database initialization error: {e}")

init_db()

# --- HELPER: AUTO-GENERATE ESR NUMBER ---
def generate_next_esr_number():
    current_year = datetime.today().strftime("%Y")
    prefix = f"ESR-{current_year}-"
    next_seq = 1
    try:
        conn = get_db_connection()
        df = pd.read_sql("SELECT esr_number FROM esr_log", conn)
        conn.close()
        if not df.empty:
            sequences = []
            for esr in df["esr_number"]:
                parts = str(esr).split("-")
                if len(parts) == 3 and parts[2].isdigit():
                    sequences.append(int(parts[2]))
            if sequences:
                next_seq = max(sequences) + 1
    except Exception:
        pass
    return f"{prefix}{next_seq:03d}"

# --- PDF GENERATOR (IN-MEMORY BYTES) ---
def generate_esr_pdf_bytes(data):
    buffer = io.BytesIO()
    c = pdf_canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    margin = 35
    content_width = width - (2 * margin)
    y = height - 35

    # Header Box matching exact format
    c.setFillColorRGB(0, 0, 0.33)  # Dark Blue
    c.rect(margin, y - 45, content_width, 45, fill=1, stroke=0)
    
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica", 12)
    c.drawString(margin + 12, y - 16, "Engineering Service Request (ESR)")
    
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(width - margin - 12, y - 16, "HES Industries")
    c.setFont("Helvetica", 8)
    c.drawRightString(width - margin - 12, y - 30, "Design, Support & Operational Intake Control")
    
    y -= 55

    def draw_section_banner(title_text):
        nonlocal y
        c.setFillColorRGB(0.88, 0.88, 0.88)
        c.rect(margin, y - 16, content_width, 16, fill=1, stroke=1)
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(margin + 6, y - 12, title_text)
        y -= 22

    def draw_field(label, val, x_offset, current_y):
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x_offset, current_y, label)
        c.setFont("Helvetica", 8)
        c.drawString(x_offset + 85, current_y, str(val)[:45] if pd.notna(val) else "")

    # SECTION 1: General Request Information
    draw_section_banner("1. General Request Information")
    
    row_y = y
    draw_field("ESR Number:", data.get("esr_number", ""), margin + 6, row_y)
    draw_field("Date Submitted:", str(data.get("date_logged", ""))[:10], margin + 240, row_y)
    y -= 16
    
    row_y = y
    draw_field("Department:", data.get("department", ""), margin + 6, row_y)
    
    c.setFont("Helvetica-Bold", 8)
    c.drawString(margin + 240, row_y, "Priority Level:")
    priorities = ["Low", "Med", "High", "Critical"]
    curr_val = str(data.get("priority_level", "Med"))
    px = margin + 315
    for p in priorities:
        c.rect(px, row_y - 1, 8, 8, fill=0, stroke=1)
        if p.lower() == curr_val.lower():
            c.setFont("Helvetica-Bold", 8)
            c.drawString(px + 1, row_y - 1, "X")
        c.setFont("Helvetica", 8)
        c.drawString(px + 11, row_y, p)
        px += 52
    y -= 16

    row_y = y
    draw_field("Originator:", data.get("originator", ""), margin + 6, row_y)
    draw_field("Project / System:", data.get("project_system", ""), margin + 240, row_y)
    y -= 22

    # SECTION 2: Scope of Service & Justification
    draw_section_banner("2. Scope of Service & Justification")
    fields_s2 = [
        ("Title of Service Request:", data.get("service_title", "")),
        ("Affected Assemblies / Parts:", data.get("affected_assemblies", "")),
        ("Current Baseline / Problem:", data.get("problem_statement", "")),
        ("Requested Deliverables:", data.get("requested_deliverables", "")),
        ("Operational Justification:", data.get("operational_justification", ""))
    ]
    
    for lbl, text_val in fields_s2:
        c.setFont("Helvetica-Bold", 8)
        c.drawString(margin + 6, y, lbl)
        y -= 12
        c.setFont("Helvetica", 8)
        text_str = str(text_val) if pd.notna(text_val) else ""
        c.rect(margin + 6, y - 18, content_width - 12, 20, fill=0, stroke=1)
        c.drawString(margin + 12, y - 12, text_str[:110])
        y -= 24

    y -= 4
    # SECTION 3: Cross-Functional Impact Assessment
    draw_section_banner("3. Cross-Functional Impact Assessment")
    c.setFillColorRGB(0.92, 0.92, 0.92)
    c.rect(margin, y - 14, content_width, 14, fill=1, stroke=1)
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(margin + 6, y - 10, "Technical Discipline")
    c.drawString(margin + 150, y - 10, "Impact Status")
    c.drawString(margin + 260, y - 10, "Scope of Modification / Review Findings")
    y -= 16

    impacts = [
        ("Mechanical Design", data.get("mechanical_impact", "Yes - Reviewed")),
        ("Electrical Engineering", data.get("electrical_impact", "No Impact")),
        ("Validation, QA & Test", data.get("qa_impact", "Pending"))
    ]

    for disc, status in impacts:
        c.rect(margin, y - 16, content_width, 16, fill=0, stroke=1)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(margin + 6, y - 12, disc)
        
        c.setFont("Helvetica", 8)
        c.rect(margin + 150, y - 12, 8, 8, fill=0, stroke=1)
        if "Yes" in status:
            c.drawString(margin + 151, y - 12, "X")
        c.drawString(margin + 163, y - 12, "Yes")
        
        c.rect(margin + 195, y - 12, 8, 8, fill=0, stroke=1)
        if "No" in status:
            c.drawString(margin + 196, y - 12, "X")
        c.drawString(margin + 208, y - 12, "No")
        
        c.drawString(margin + 260, y - 12, status)
        y -= 16

    y -= 8
    # SECTION 4: Risk & Lessons Learned Documentation
    draw_section_banner("4. Risk & Lessons Learned Documentation")
    risks = [
        ("Technical Risk Assessments & Manufacturing Potentials:", data.get("technical_risk", "")),
        ("Mitigation & Contingency Engineering Measures:", data.get("mitigation_measures", ""))
    ]
    
    for lbl, r_val in risks:
        c.setFont("Helvetica-Bold", 8)
        c.drawString(margin + 6, y, lbl)
        y -= 12
        c.setFont("Helvetica", 8)
        c.rect(margin + 6, y - 18, content_width - 12, 20, fill=0, stroke=1)
        c.drawString(margin + 12, y - 12, str(r_val)[:110] if pd.notna(r_val) else "")
        y -= 24

    y -= 4

    # SECTION 4.1: Action Logs from DB
    try:
        conn = get_db_connection()
        df_actions = pd.read_sql("SELECT * FROM esr_action_log WHERE esr_number = %s", conn, params=(data.get("esr_number"),))
        conn.close()
        if not df_actions.empty:
            draw_section_banner("4.1. Engineering Drawing Changes & Action Log")
            c.setFillColorRGB(0.92, 0.92, 0.92)
            c.rect(margin, y - 14, content_width, 14, fill=1, stroke=1)
            c.setFillColorRGB(0, 0, 0)
            c.setFont("Helvetica-Bold", 7)
            c.drawString(margin + 6, y - 10, "Date")
            c.drawString(margin + 75, y - 10, "Engineer")
            c.drawString(margin + 160, y - 10, "Category")
            c.drawString(margin + 270, y - 10, "Changed Drawings")
            c.drawString(margin + 390, y - 10, "Implementation Notes")
            y -= 16

            for _, act_row in df_actions.iterrows():
                c.rect(margin, y - 16, content_width, 16, fill=0, stroke=1)
                c.setFont("Helvetica", 7)
                c.drawString(margin + 6, y - 11, str(act_row.get("action_date", ""))[:10])
                c.drawString(margin + 75, y - 11, str(act_row.get("engineer", ""))[:20])
                c.drawString(margin + 160, y - 11, str(act_row.get("category", ""))[:22])
                c.drawString(margin + 270, y - 11, str(act_row.get("changed_drawings", ""))[:22])
                c.drawString(margin + 390, y - 11, str(act_row.get("notes", ""))[:32])
                y -= 16
            y -= 4
    except Exception:
        pass

    y -= 4
    # SECTION 5: Change Review Board (CRB) Routing & Sign-off
    draw_section_banner("5. Change Review Board (CRB) Routing & Sign-off")
    c.setFont("Helvetica", 7)
    c.drawString(margin + 6, y, "By signing below, leads verify that the request has been evaluated within their respective resource boundaries.")
    y -= 14

    c.setFillColorRGB(0.92, 0.92, 0.92)
    c.rect(margin, y - 16, content_width, 16, fill=1, stroke=1)
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(margin + 6, y - 12, "Discipline Review Authority")
    c.drawString(margin + 160, y - 12, "Disposition Action")
    c.drawString(margin + 330, y - 12, "Signature / Authorization")
    c.drawString(margin + 460, y - 12, "Date")
    y -= 16

    signoffs = [
        ("Mechanical Design Lead", data.get("mech_signoff", "Approved")),
        ("Electrical Engineering Lead", data.get("elec_signoff", "N/A")),
        ("Validation & QA Lead", data.get("qa_signoff", "Pending")),
        ("Project / Operations Manager", data.get("manager_signoff", "Pending"))
    ]

    for role, sign_val in signoffs:
        c.rect(margin, y - 22, content_width, 22, fill=0, stroke=1)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(margin + 6, y - 14, role)
        
        s_val_str = str(sign_val) if pd.notna(sign_val) else ""
        c.setFont("Helvetica", 7)
        c.rect(margin + 160, y - 15, 7, 7, fill=0, stroke=1)
        if "Approv" in s_val_str or "Author" in s_val_str:
            c.drawString(margin + 161, y - 15, "X")
        c.drawString(margin + 172, y - 14, "Appr/Auth")

        c.rect(margin + 225, y - 15, 7, 7, fill=0, stroke=1)
        if "Reject" in s_val_str:
            c.drawString(margin + 226, y - 15, "X")
        c.drawString(margin + 237, y - 14, "Reject")

        c.rect(margin + 280, y - 15, 7, 7, fill=0, stroke=1)
        if "N/A" in s_val_str or "Pend" in s_val_str:
            c.drawString(margin + 281, y - 15, "X")
        c.drawString(margin + 292, y - 14, "N/A / Pend")

        c.drawString(margin + 330, y - 14, s_val_str)
        y -= 22

    c.save()
    buffer.seek(0)
    return buffer.getvalue()

# --- APP UI HEADER ---
st.title("Hybrid Electrostatic Industries — Master Log Manager")
st.markdown("**ESR Intake Form & Engineering Change Control System**")
st.divider()

# Navigation Tabs
tab_add, tab_view = st.tabs(["  ➕ Create ESR Form  ", "  📋 View & Manage ESR Log  "])

# --- TAB 1: CREATE ESR FORM ---
with tab_add:
    st.subheader("1. General Request Information")
    with st.form("create_esr_form"):
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            esr_number = st.text_input("ESR Number", value=generate_next_esr_number())
            originator = st.text_input("Originator", value="Michael Konyak")
        with col2:
            date_submitted = st.date_input("Date Submitted", value=date.today())
            project_system = st.text_input("Project / System", value="HES Standard System")
        with col3:
            department = st.text_input("Department", value="Mechanical Engineering")
            product_name = st.text_input("Product Name", value="")
        with col4:
            priority_level = st.selectbox("Priority Level", ["Low", "Med", "High", "Critical"], index=1)
            
        st.subheader("2. Scope of Service & Justification")
        service_title = st.text_input("Service Title")
        affected_assemblies = st.text_area("Affected Assemblies / Parts")
        problem_statement = st.text_area("Current Baseline / Problem Statement")
        requested_deliverables = st.text_area("Requested Deliverables")
        operational_justification = st.text_area("Operational Justification")
        
        st.subheader("3. Cross-Functional Impact Assessment")
        col_i1, col_i2, col_i3 = st.columns(3)
        with col_i1:
            mech_impact = st.selectbox("Mechanical Design Impact", ["Yes - Reviewed", "No Impact", "Pending"])
        with col_i2:
            elec_impact = st.selectbox("Electrical Engineering Impact", ["Yes - Reviewed", "No Impact", "Pending"], index=1)
        with col_i3:
            qa_impact = st.selectbox("Validation, QA & Test Impact", ["Yes - Reviewed", "No Impact", "Pending"], index=2)
            
        st.subheader("4. Risk & Lessons Learned Documentation")
        technical_risk = st.text_area("Technical Risk / Mfg Potentials")
        mitigation_measures = st.text_area("Mitigation & Contingency Measures")
        
        st.subheader("5. Change Review Board (CRB) Routing & Sign-off")
        col_s1, col_s2, col_s3, col_s4, col_s5 = st.columns(5)
        with col_s1:
            mech_signoff = st.selectbox("Mechanical Lead", ["Approved", "Rejected", "N/A", "Pending"])
        with col_s2:
            elec_signoff = st.selectbox("Electrical Lead", ["Approved", "Rejected", "N/A", "Pending"], index=2)
        with col_s3:
            qa_signoff = st.selectbox("QA Lead", ["Approved", "Rejected", "N/A", "Pending"], index=3)
        with col_s4:
            manager_signoff = st.selectbox("Operations Manager", ["Authorized", "Rejected", "Pending"], index=2)
        with col_s5:
            status = st.selectbox("Overall Status", ["Pending Review", "In Progress", "Completed", "Cancelled"])
            
        submitted = st.form_submit_button("🚀 Submit ESR & Generate PDF", use_container_width=True)
        
        if submitted:
            if not esr_number or not service_title:
                st.error("ESR Number and Service Title are required.")
            else:
                data_dict = {
                    "esr_number": esr_number,
                    "date_logged": str(date_submitted),
                    "department": department,
                    "priority_level": priority_level,
                    "originator": originator,
                    "project_system": project_system,
                    "product_name": product_name,
                    "service_title": service_title,
                    "affected_assemblies": affected_assemblies,
                    "problem_statement": problem_statement,
                    "requested_deliverables": requested_deliverables,
                    "operational_justification": operational_justification,
                    "mechanical_impact": mech_impact,
                    "electrical_impact": elec_impact,
                    "qa_impact": qa_impact,
                    "technical_risk": technical_risk,
                    "mitigation_measures": mitigation_measures,
                    "mech_signoff": mech_signoff,
                    "elec_signoff": elec_signoff,
                    "qa_signoff": qa_signoff,
                    "manager_signoff": manager_signoff,
                    "status": status
                }
                try:
                    conn = get_db_connection()
                    cur = conn.cursor()
                    cur.execute("""
                        INSERT INTO esr_log (
                            esr_number, date_logged, department, priority_level, originator, 
                            project_system, product_name, service_title, affected_assemblies, 
                            problem_statement, requested_deliverables, operational_justification, 
                            mechanical_impact, electrical_impact, qa_impact, technical_risk, 
                            mitigation_measures, mech_signoff, elec_signoff, qa_signoff, 
                            manager_signoff, status
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        ) ON CONFLICT (esr_number) DO UPDATE SET
                            date_logged = EXCLUDED.date_logged, department = EXCLUDED.department,
                            priority_level = EXCLUDED.priority_level, originator = EXCLUDED.originator,
                            project_system = EXCLUDED.project_system, product_name = EXCLUDED.product_name,
                            service_title = EXCLUDED.service_title, affected_assemblies = EXCLUDED.affected_assemblies,
                            problem_statement = EXCLUDED.problem_statement, requested_deliverables = EXCLUDED.requested_deliverables,
                            operational_justification = EXCLUDED.operational_justification, mechanical_impact = EXCLUDED.mechanical_impact,
                            electrical_impact = EXCLUDED.electrical_impact, qa_impact = EXCLUDED.qa_impact,
                            technical_risk = EXCLUDED.technical_risk, mitigation_measures = EXCLUDED.mitigation_measures,
                            mech_signoff = EXCLUDED.mech_signoff, elec_signoff = EXCLUDED.elec_signoff,
                            qa_signoff = EXCLUDED.qa_signoff, manager_signoff = EXCLUDED.manager_signoff, status = EXCLUDED.status;
                    """, (
                        data_dict["esr_number"], data_dict["date_logged"], data_dict["department"],
                        data_dict["priority_level"], data_dict["originator"], data_dict["project_system"],
                        data_dict["product_name"], data_dict["service_title"], data_dict["affected_assemblies"],
                        data_dict["problem_statement"], data_dict["requested_deliverables"], data_dict["operational_justification"],
                        data_dict["mechanical_impact"], data_dict["electrical_impact"], data_dict["qa_impact"],
                        data_dict["technical_risk"], data_dict["mitigation_measures"], data_dict["mech_signoff"],
                        data_dict["elec_signoff"], data_dict["qa_signoff"], data_dict["manager_signoff"], data_dict["status"]
                    ))
                    conn.commit()
                    cur.close()
                    conn.close()
                    
                    st.success(f"ESR {esr_number} successfully submitted and saved to Supabase!")
                    # Store data in session state so download button can live OUTSIDE the form
                    st.session_state["last_saved_esr"] = data_dict
                except Exception as e:
                    st.error(f"Failed to save record to database: {e}")

    # Render download button OUTSIDE the form block using session state
    if "last_saved_esr" in st.session_state:
        saved_data = st.session_state["last_saved_esr"]
        pdf_bytes = generate_esr_pdf_bytes(saved_data)
        st.download_button(
            label=f"📄 Download Official ESR PDF Form ({saved_data['esr_number']})",
            data=pdf_bytes,
            file_name=f"{saved_data['esr_number']}.pdf",
            mime="application/pdf",
            use_container_width=True
        )

# --- TAB 2: VIEW & MANAGE ESR LOG ---
with tab_view:
    st.subheader("Active Engineering Change Requests")
    
    try:
        conn = get_db_connection()
        df_esr = pd.read_sql("SELECT * FROM esr_log ORDER BY date_logged DESC", conn)
        conn.close()
        
        if not df_esr.empty:
            search_query = st.text_input("🔍 Filter / Search Records", "")
            if search_query:
                mask = df_esr.apply(lambda row: row.astype(str).str.contains(search_query, case=False).any(), axis=1)
                df_display = df_esr[mask]
            else:
                df_display = df_esr
                
            st.dataframe(df_display, use_container_width=True)
            
            st.divider()
            st.subheader("Record Management & Action Logs")
            selected_esr = st.selectbox("Select ESR Number to View / Modify / Export", df_esr["esr_number"].tolist())
            
            if selected_esr:
                row_data = df_esr[df_esr["esr_number"] == selected_esr].iloc[0].to_dict()
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    pdf_data = generate_esr_pdf_bytes(row_data)
                    st.download_button(
                        label=f"📄 Download PDF for {selected_esr}",
                        data=pdf_data,
                        file_name=f"{selected_esr}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                
                with col_btn2:
                    if st.button("⚙️ Log Drawing Change / Action Item", use_container_width=True):
                        st.session_state["logging_action_for"] = selected_esr
                
                # Action log form expander if triggered
                if st.session_state.get("logging_action_for") == selected_esr:
                    with st.form(f"action_form_{selected_esr}"):
                        st.markdown(f"**Log Drawing Change for {selected_esr}**")
                        act_date = st.date_input("Action Date", value=date.today())
                        engineer = st.text_input("Engineer Name", value="Michael Konyak")
                        category = st.selectbox("Change Category", [
                            "Drawing Revision Updated", "CAD Model Modified", 
                            "BOM Revised", "Schematic Updated", "Red-Line Implemented"
                        ])
                        changed_drawings = st.text_input("Changed Drawing Numbers")
                        notes = st.text_area("Drawing Change Notes & Details")
                        
                        if st.form_submit_button("💾 Save Action Log"):
                            try:
                                conn = get_db_connection()
                                cur = conn.cursor()
                                cur.execute("""
                                    INSERT INTO esr_action_log (esr_number, action_date, engineer, category, changed_drawings, notes)
                                    VALUES (%s, %s, %s, %s, %s, %s);
                                """, (selected_esr, str(act_date), engineer, category, changed_drawings, notes))
                                conn.commit()
                                cur.close()
                                conn.close()
                                st.success("Action logged successfully!")
                                st.session_state["logging_action_for"] = None
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error saving action log: {e}")
                                
                # Display existing action logs for this ESR
                try:
                    conn = get_db_connection()
                    df_actions = pd.read_sql("SELECT action_date, engineer, category, changed_drawings, notes FROM esr_action_log WHERE esr_number = %s", conn, params=(selected_esr,))
                    conn.close()
                    if not df_actions.empty:
                        st.markdown(f"**Associated Drawing Changes & Action Logs for {selected_esr}:**")
                        st.dataframe(df_actions, use_container_width=True)
                except Exception:
                    pass
        else:
            st.info("No ESR records found in the Supabase database yet. Create one using the form tab!")
    except Exception as e:
        st.error(f"Could not load data from database: {e}")