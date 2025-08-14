import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import os
from utils import db_utils
from utils.calculator import calculate_subtotal, calculate_gst, calculate_discount, calculate_total


def show_clock():
    st.sidebar.markdown(f"### 🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# ------------------ ORDER PAGE ------------------
def page_order():
    st.header("Place Order")
    show_clock()

    menu_df = db_utils.load_menu_df()
    if menu_df.empty:
        st.warning("Menu is empty. Please import menu.csv from DB Setup or add items in Admin.")
        return

    # Table management
    st.sidebar.header("Table Management")
    tables_df = db_utils.get_tables_df()
    if not tables_df.empty:
        for _, row in tables_df.iterrows():
            status = row["status"]
            color = "🟢" if status == "available" else ("🔴" if status == "occupied" else "🟠")
            st.sidebar.markdown(
             f"{color} **{row['name']}** — {status} "
             f"{'(Order #'+str(int(row['current_order_id']))+')' if pd.notna(row['current_order_id']) else ''}"
)



    # Order type and payment
    order_type = st.radio("Order type", ["Dine-In", "Takeaway"], horizontal=True)
    payment_mode = st.selectbox("Payment method", ["Cash", "Card", "UPI"])

    selected_table_id = None
    if order_type == "Dine-In" and not tables_df.empty:
        avail = tables_df[tables_df["status"] == "available"]
        if not avail.empty:
            sel = st.selectbox("Choose table", options=avail["name"].tolist())
            selected_table_id = int(avail[avail["name"] == sel]["id"].iloc[0])
        else:
            st.warning("No available tables.")

    # Menu
    st.subheader("Menu")
    categories = menu_df["category"].unique()
    selected_items = []

    # Column headers
    col1_header, col2_header, col3_header = st.columns([1, 4, 1])
    col1_header.markdown("**Category**")
    col2_header.markdown("**Item**")
    col3_header.markdown("**Quantity**")


    for cat in categories:
        st.markdown(f"**{cat}**")
        cat_items = menu_df[menu_df["category"] == cat]
        for _, row in cat_items.iterrows():
            col1, col2, col3 = st.columns([1, 4, 1])

            with col2:
                price_str = f"{row['price']:.2f}".rstrip('0').rstrip('.')  # remove .00 if unnecessary
                st.markdown(f"**{row['item_name']}**")
                st.caption(f"{row['category']} • {price_str} DA • GST {int(row['gst'])}%")
            with col3:
                quantity = st.number_input( label="", min_value=0, step=1, value=0, key=f"quantity_{int(row['id'])}"  
            )

                    
                
                if quantity > 0:
                    selected_items.append({
                        "item_id": int(row["id"]),
                        "name": row["item_name"],
                        "price": float(row["price"]),
                        "quantity": int(quantity),
                        "gst": int(row["gst"]),
                        "category": row["category"]
                    })

    if not selected_items:
        st.info("Select items and quantities to build the order.")
        return

    # Summary
    st.subheader("Order Summary")
    summary_df = pd.DataFrame(selected_items)
    summary_df["line_total"] = summary_df["price"] * summary_df["quantity"]
    summary_df_display = summary_df.rename(columns={"name": "Item", "price": "Price", "quantity": "Qty", "line_total": "Total"})
    st.table(summary_df_display)

    subtotal = calculate_subtotal(selected_items)
    gst_amount = calculate_gst(subtotal, gst_rate=5)

    discount_type = st.selectbox("Discount type", ["None", "Percentage", "Fixed amount"])
    discount_amount = 0.0
    if discount_type == "Percentage":
        pct = st.number_input("Discount (%)", min_value=0.0, max_value=100.0, value=0.0)
        discount_amount = calculate_discount(subtotal, "Percentage", pct)
    elif discount_type == "Fixed amount":
        amt = st.number_input("Discount amount (DA)", min_value=0.0, value=0.0)
        discount_amount = calculate_discount(subtotal, "Fixed amount", amt)

    total = calculate_total(subtotal, gst_amount, discount_amount)

    st.write(f"Subtotal: **{subtotal:.2f} DA**")
    st.write(f"GST (5%): **{gst_amount:.2f} DA**")
    if discount_amount > 0:
        st.write(f"Discount: **-{discount_amount:.2f} DA**")
    st.write(f"Total: **{total:.2f} DA**")

    if st.button("Confirm & Save Order"):
        order_id = db_utils.save_order(
            order_type, payment_mode, subtotal, gst_amount, discount_amount, total, selected_items, table_id=selected_table_id
        )
        st.success(f"Order saved with ID #{order_id}")
        if order_type == "Dine-In" and selected_table_id:
            db_utils.update_table_status(selected_table_id, "occupied", current_order_id=order_id)

# ------------------ REPORTS PAGE ------------------
def page_reports():
    st.header("Sales Reports and Most Sold Items")
    today = datetime.now().date()
    period = st.selectbox("Select period", ["Daily", "Weekly", "Monthly", "Custom Range"])
    if period == "Daily":
        start = end = today
    elif period == "Weekly":
        start, end = today - timedelta(days=7), today
    elif period == "Monthly":
        start, end = today.replace(day=1), today
    else:
        start = st.date_input("Start date", value=today - timedelta(days=7))
        end = st.date_input("End date", value=today)

    df = db_utils.get_sales_dataframe(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    if df.empty:
        st.info("No sales in selected period.")
        return

    st.metric("Total sales (DA)", f"{df['line_total'].sum():.2f}")
    st.metric("Total orders", int(df["order_id"].nunique()))
    st.subheader("Sales items")
    st.dataframe(df[["order_id","order_date","item_name","category","quantity","price","line_total"]])

    ms = db_utils.most_sold_items_df(df, top_n=20)
    if not ms.empty:
        st.subheader("Most sold items")
        st.table(ms.rename(columns={"item_name":"Item","quantity":"Quantity"}))

# ------------------ ADMIN PAGE ------------------

def page_admin():
    st.header("Admin - Manage Menu and Tables")

    st.subheader("Menu")
    menu_df = db_utils.load_menu_df()
    if not menu_df.empty:
        menu_df_display = menu_df.copy()
        menu_df_display["price"] = menu_df_display["price"].apply(lambda x: f"{x:.2f}".rstrip('0').rstrip('.'))
      
        for _, row in menu_df_display.iterrows():
            col1, col2, col3, col4 = st.columns([1, 3, 2, 2])
            col1.write(int(row["id"]))  # ID first
            col2.write(row["item_name"])
            col3.write(row["category"])
            col4.write(f"{row['price']} DA")
            if row.get("image") and os.path.exists(row["image"]):
                st.image(row["image"], width=80)

    # Initialize action state
    if "action" not in st.session_state:
        st.session_state["action"] = None

    # Buttons to select action
    col1, col2, col3 = st.columns([1,1,1])
    if col1.button("Add Menu Item"):
        st.session_state["action"] = "add"
    if col2.button("Edit Menu Item"):
        st.session_state["action"] = "edit"
    if col3.button("Delete Menu Item"):
        st.session_state["action"] = "delete"

    st.markdown("---")  
    # separator

    if st.session_state["action"] == "add":
        st.subheader("Add Menu Item")
        with st.form("add_item_form", clear_on_submit=True):
            name = st.text_input("Name")
            cat = st.text_input("Category")
            price = st.number_input("Price (DA)", min_value=0.0, value=100.0)
            gst = st.number_input("GST (%)", min_value=0, max_value=100, value=5)
            image = st.text_input("Image path (optional)")
            if st.form_submit_button("Add"):
                db_utils.add_menu_item(name, cat, price, gst, image if image else None)
                st.success("Item added. Please refresh to see it in the menu.")
                st.session_state["action"] = None

    elif st.session_state["action"] == "edit":
        item_id = st.number_input("Enter Menu Item ID to edit", min_value=1, step=1, key="edit_item_id")

        if item_id:
            # Find item in menu_df 
            item_row = menu_df[menu_df["id"] == item_id]
            if not item_row.empty:
                item = item_row.iloc[0]  
                with st.form("edit_item_form", clear_on_submit=False):
                    name = st.text_input("Name", value=item["item_name"])
                    cat = st.text_input("Category", value=item["category"])
                    price = st.number_input("Price (DA)", min_value=0.0, value=float(item["price"]))
                    gst = st.number_input("GST (%)", min_value=0, max_value=100, value=int(item.get("gst", 5)))
                    image = st.text_input("Image path (optional)", value=item.get("image", ""))
                    if st.form_submit_button("Save changes"):
            # Update function with new data
                        db_utils.update_menu_item(item_id, name, cat, price, gst, image if image else None)
                        st.success(f"Item ID {item_id} updated. Please refresh to see changes.")
                        st.session_state["action"] = None
            else:
                st.error(f"No item found with ID {item_id}")

    elif st.session_state["action"] == "delete":
        item_id = st.number_input("Enter Menu Item ID to delete", min_value=1, step=1, key="delete_item_id")

        if item_id:
            confirm = st.checkbox(f"Confirm delete item ID {item_id}", key="confirm_delete_checkbox")

            if confirm:
                if st.button("Delete item", key="delete_item_button"):
                    db_utils.delete_menu_item(item_id)
                    st.warning(f"Item ID {item_id} deleted. Please refresh to see changes.")
                    st.session_state["action"] = None
                    st.session_state["confirm_delete_checkbox"] = False

    st.subheader("Tables")
    tables_df = db_utils.get_tables_df()
    if not tables_df.empty:
        st.dataframe(
        tables_df[["id", "name", "capacity", "status"]],
        hide_index=True 
        )
     # Sidebar Add Table form
    st.sidebar.markdown("---")
    st.sidebar.subheader("Add Table")
    with st.sidebar.form("add_table_form", clear_on_submit=True):
        default_name = f"T{len(tables_df) + 1}" if not tables_df.empty else "T1"
        tname = st.text_input("Table name", value=default_name)
        tcap = st.number_input("Capacity", min_value=1, value=2)
        if st.form_submit_button("Add Table"):
            db_utils.add_table(tname, tcap)
            st.success("Table added. Refresh to see it.")

     # Sidebar Delete Table form
    st.sidebar.markdown("---")
    st.sidebar.subheader("Delete Table")
    with st.sidebar.form("delete_table_form", clear_on_submit=True):
        del_tname = st.text_input("Table name to delete")
        if st.form_submit_button("Delete Table"):
            if del_tname:
                success = db_utils.delete_table(del_tname)  
                if success:
                    st.success(f"Table '{del_tname}' deleted. Refresh to see changes.")
                else:
                    st.error(f"Table '{del_tname}' not found.")
            else:
                st.error("Please enter a table name.")



# ------------------ RENDER ------------------
def render(page_name):
    if page_name == "Order":
        page_order()
    elif page_name == "Reports":
        page_reports()
    elif page_name == "Admin":
        page_admin()
