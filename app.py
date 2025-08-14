import os
import streamlit as st
from utils import db_utils
from ui import main_ui  

DB_PATH = "data/database.db"

if not os.path.exists(DB_PATH):
    db_utils.initialize_database()
    db_utils.populate_menu_from_csv()

st.set_page_config(page_title="Restaurant Billing System", layout="wide")
st.title("Restaurant Billing System")

menu = ["Home", "Order", "Reports", "Admin"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Home":
    st.subheader("Menu")

    # Load menu items from database
    df = db_utils.load_menu_df()

    if df.empty:
        st.info("Menu is empty. Please add items from Admin panel.")
    else:
        for _, row in df.iterrows():
            col1, col2 = st.columns([1, 3])

            # Build full image path
            image_path = os.path.join("data/images", row["image"]) if row["image"] else None

            if image_path and os.path.exists(image_path):
                col1.image(image_path, width=100)
            else:
                col1.write("No image")

            # Item details
            col2.markdown(f"**{row['item_name']}**")
            col2.markdown(f"Price: DA {row['price']:.2f}")

            st.markdown("---")
else:
    main_ui.render(choice)


