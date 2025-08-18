import streamlit as st
from pathlib import Path
from config import BASE_DIR
from auth_db import check_authentication, show_login_page, logout_user, auth_db

st.set_page_config(page_title="Radical Reactions Platform (Buxton)", layout="wide")

# Check authentication status
print(f"[MAIN PAGE] Starting main page load")
print(f"[MAIN PAGE] Session state page_mode: {st.session_state.get('page_mode', 'main')}")
current_user = check_authentication()
print(f"[MAIN PAGE] Current user from check_authentication(): {current_user}")

# === CHECK IF WE'RE IN VALIDATION MODE ===
if st.session_state.get('page_mode') == 'validate':
    print(f"[MAIN PAGE] Entering validation mode")
    
    # Check authentication for validation page
    if not current_user:
        st.error("❌ **Authentication Required for Validation**")
        st.info("Your session may have expired. Please log in again.")
        st.session_state.page_mode = 'main'  # Return to main page
        st.rerun()
    
    # Show validation interface
    from validate_embedded import show_validation_interface
    show_validation_interface(current_user)
    st.stop()  # Don't show main page content

# === HEADER WITH LOGIN/LOGOUT ===
header_col1, header_col2 = st.columns([3, 1])

with header_col1:
    st.title("Radical Reactions Platform")
    st.subheader("Digitizing and validating radiation radical reactions from Buxton Critical Review")

with header_col2:
    if current_user:
        st.success(f"👤 Logged in as: **{current_user}**")
        if st.button("🚪 Logout", type="secondary"):
            logout_user()
            st.rerun()
    else:
        if st.button("🔐 Login", type="primary"):
            st.session_state.show_login = True
            st.rerun()

st.markdown("---")

# === LOGIN FORM (if requested) ===
if st.session_state.get('show_login', False) and not current_user:
    st.header("🔐 Login")
    
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        login_col1, login_col2 = st.columns([1, 1])
        
        with login_col1:
            submit_button = st.form_submit_button("Login", type="primary")
        with login_col2:
            cancel_button = st.form_submit_button("Cancel")
        
        if cancel_button:
            st.session_state.show_login = False
            st.rerun()
            
        if submit_button:
            if username and password:
                success, message = auth_db.authenticate_user(username, password)
                if success:
                    from auth_db import login_user
                    login_user(username)
                    st.session_state.show_login = False
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)
            else:
                st.error("Please enter both username and password")
    
    st.markdown("---")
    st.markdown("### New User Registration")
    st.markdown("To request a new account, please email **sergey.denisov@universite-paris-saclay.fr** with:")
    st.markdown("- Requested username")
    st.markdown("- Your institutional email")
    st.markdown("- Justification for access")
    
    st.stop()  # Don't show the rest of the page during login

# === MAIN CONTENT ===
col1, col2 = st.columns([2, 1])
with col1:
    st.markdown(
        """
        This project develops an open platform for radiation radical reactions, initially curated from the Buxton Critical Review of Rate Constants for Reactions of Hydrated Electrons, Hydrogen Atoms and Hydroxyl Radicals in Aqueous Solution (DOI: 10.1063/1.555805). The workflow is:
        
        - Extract and correct TSV files from table images
        - Generate LaTeX/PDF for human-readable rendering
        - Validate entries collaboratively
        - Publish a searchable database of reactions
        """
    )

with col2:
    if current_user:
        st.success(
            "✅ You are logged in! You can access the validation workflow to "
            "validate OCR results and contribute to the database."
        )
        # Use session-state based navigation to preserve authentication
        st.markdown(
            """
            ### 🔍 Access Validation Workflow
            """
        )
        
        if st.button("🔍 Go to Validation Page", type="primary", use_container_width=True):
            print(f"[MAIN PAGE] User clicked validation button, setting page_mode to 'validate'")
            st.session_state.page_mode = 'validate'
            st.rerun()
    else:
        st.info(
            "👆 Login above to access the validation workflow. "
            "Public users can search the database below."
        )

st.markdown("---")

# === SEARCH SECTION ===
st.header("🔍 Search Reactions Database")

if current_user:
    st.info("🔓 Authenticated Search: full access to DB and advanced filters.")
else:
    st.info("🌐 Public Search: basic search across reactions DB.")

query = st.text_input("Search reactions (text or formula)", placeholder="e.g. e_aq^- OH•, hydroxyl, O2•-", key="search_query")
max_hits = st.number_input("Max results", min_value=1, max_value=200, value=25, step=1)

# Filters
with st.expander("🔧 Advanced Search Options"):
    table_filter = st.selectbox("Table (category)", options=["All", 5,6,7,8,9], format_func=lambda x: {"All":"All",5:"Table5 (water radiolysis)",6:"Table6 (e_aq^-) ",7:"Table7 (H•)",8:"Table8 (OH•)",9:"Table9 (O•−)"}[x] if x!="All" else "All")

if query:
    from reactions_db import ensure_db, search_reactions, count_reactions
    con = ensure_db()
    table_no = None if table_filter == "All" else int(table_filter)
    try:
        rows = search_reactions(con, query, table_no=table_no, limit=int(max_hits))
    except Exception as e:
        st.error(f"DB search error: {e}")
        rows = []
    st.write(f"Found {len(rows)} matches")
    if rows:
        for i, r in enumerate(rows, 1):
            with st.expander(f"Result {i}: {r['formula_canonical']}"):
                st.markdown(f"**Table:** {r['table_no']} ({r['table_category']})")
                if r['reaction_name']:
                    st.markdown(f"**Name:** {r['reaction_name']}")
                st.latex(r['formula_latex'])
                st.code(f"Reactants: {r['reactants']}\nProducts: {r['products']}")
                if r['notes']:
                    st.markdown(f"**Notes:** {r['notes']}")
    else:
        st.info("No results found. Try different search terms.")
else:
    st.info("Enter a search term above to find reactions.")
