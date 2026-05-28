
# -*- coding: utf-8 -*-
"""
demo_seed.py
Purpose:
    Safe, repeatable demo data pack for Pharma Quick Sale / Pharma SFA v26.

Run:
    bench --site <site-name> execute pharma_quick_sale.demo.demo_seed.seed_all

Design principles:
    - Uses ERPNext/Frappe DocType APIs, not raw SQL inserts.
    - Checks for existing records before create.
    - Avoids mandatory-field failures by reading company defaults where possible.
    - Uses conservative stock/invoice paths.
    - Can be re-run safely for demo refresh.
"""

import frappe
from frappe.utils import nowdate, add_days, getdate, flt


DEMO_PREFIX = "PQS-DEMO"


def log(msg):
    frappe.logger("pharma_demo_seed").info(msg)
    print(msg)


def exists(doctype, name):
    return bool(frappe.db.exists(doctype, name))


def get_or_create_doc(doctype, name=None, **values):
    """Generic helper for simple master records."""
    docname = name or values.get("name") or values.get("title") or values.get("company_name")
    if docname and frappe.db.exists(doctype, docname):
        return frappe.get_doc(doctype, docname)

    doc = frappe.new_doc(doctype)
    for key, value in values.items():
        if value is not None and frappe.get_meta(doctype).has_field(key):
            doc.set(key, value)
    if name and frappe.get_meta(doctype).has_field("name"):
        doc.name = name
    doc.insert(ignore_permissions=True)
    return doc


def get_company():
    company = frappe.db.get_single_value("Global Defaults", "default_company")
    if company:
        return company

    company = frappe.db.get_value("Company", {}, "name")
    if company:
        return company

    raise frappe.ValidationError("No Company exists. Create a Company before running demo seed.")


def get_abbr(company):
    return frappe.db.get_value("Company", company, "abbr")


def get_currency(company):
    return frappe.db.get_value("Company", company, "default_currency") or frappe.db.get_single_value("Global Defaults", "default_currency") or "INR"


def get_income_account(company):
    acc = frappe.db.get_value("Company", company, "default_income_account")
    if acc:
        return acc
    acc = frappe.db.get_value("Account", {"company": company, "root_type": "Income", "is_group": 0}, "name")
    if not acc:
        raise frappe.ValidationError(f"No income account found for {company}.")
    return acc


def get_expense_account(company):
    acc = frappe.db.get_value("Company", company, "default_expense_account")
    if acc:
        return acc
    acc = frappe.db.get_value("Account", {"company": company, "root_type": "Expense", "is_group": 0}, "name")
    if not acc:
        raise frappe.ValidationError(f"No expense account found for {company}.")
    return acc


def get_receivable_account(company):
    acc = frappe.db.get_value("Company", company, "default_receivable_account")
    if acc:
        return acc
    acc = frappe.db.get_value("Account", {"company": company, "account_type": "Receivable", "is_group": 0}, "name")
    if not acc:
        raise frappe.ValidationError(f"No receivable account found for {company}.")
    return acc


def ensure_item_group(name):
    if frappe.db.exists("Item Group", name):
        return name
    doc = frappe.new_doc("Item Group")
    doc.item_group_name = name
    doc.parent_item_group = "All Item Groups" if frappe.db.exists("Item Group", "All Item Groups") else None
    doc.is_group = 0
    doc.insert(ignore_permissions=True)
    return doc.name


def ensure_uom(name):
    if frappe.db.exists("UOM", name):
        return name
    doc = frappe.new_doc("UOM")
    doc.uom_name = name
    doc.insert(ignore_permissions=True)
    return doc.name


def ensure_warehouse(name, company):
    if frappe.db.exists("Warehouse", name):
        return name
    abbr = get_abbr(company)
    parent = f"All Warehouses - {abbr}" if frappe.db.exists("Warehouse", f"All Warehouses - {abbr}") else None
    wh = frappe.new_doc("Warehouse")
    wh.warehouse_name = name.replace(f" - {abbr}", "")
    wh.company = company
    wh.parent_warehouse = parent
    wh.insert(ignore_permissions=True)
    return wh.name


def ensure_customer_group(name):
    if frappe.db.exists("Customer Group", name):
        return name
    doc = frappe.new_doc("Customer Group")
    doc.customer_group_name = name
    doc.parent_customer_group = "All Customer Groups" if frappe.db.exists("Customer Group", "All Customer Groups") else None
    doc.is_group = 0
    doc.insert(ignore_permissions=True)
    return doc.name


def ensure_supplier_group(name):
    if frappe.db.exists("Supplier Group", name):
        return name
    doc = frappe.new_doc("Supplier Group")
    doc.supplier_group_name = name
    doc.parent_supplier_group = "All Supplier Groups" if frappe.db.exists("Supplier Group", "All Supplier Groups") else None
    doc.is_group = 0
    doc.insert(ignore_permissions=True)
    return doc.name


def ensure_territory(name):
    if frappe.db.exists("Territory", name):
        return name
    doc = frappe.new_doc("Territory")
    doc.territory_name = name
    doc.parent_territory = "All Territories" if frappe.db.exists("Territory", "All Territories") else None
    doc.is_group = 0
    doc.insert(ignore_permissions=True)
    return doc.name


def ensure_sales_person(name, parent=None):
    if frappe.db.exists("Sales Person", name):
        return name
    doc = frappe.new_doc("Sales Person")
    doc.sales_person_name = name
    doc.parent_sales_person = parent or ("Sales Team" if frappe.db.exists("Sales Person", "Sales Team") else None)
    doc.enabled = 1
    doc.is_group = 0
    doc.insert(ignore_permissions=True)
    return doc.name


def ensure_customer(name, territory, customer_group="PQS Demo Distributors"):
    if frappe.db.exists("Customer", name):
        return name
    doc = frappe.new_doc("Customer")
    doc.customer_name = name
    doc.customer_type = "Company"
    doc.customer_group = ensure_customer_group(customer_group)
    doc.territory = ensure_territory(territory)
    doc.insert(ignore_permissions=True)
    if frappe.get_meta("Customer").has_field("pharma_drug_license_no"):
        doc.db_set("pharma_drug_license_no", f"DL-{name[-3:].upper()}-2026")
    if frappe.get_meta("Customer").has_field("pharma_drug_license_expiry"):
        doc.db_set("pharma_drug_license_expiry", add_days(nowdate(), 365))
    return doc.name


def ensure_supplier(name):
    if frappe.db.exists("Supplier", name):
        return name
    doc = frappe.new_doc("Supplier")
    doc.supplier_name = name
    doc.supplier_group = ensure_supplier_group("PQS Demo Suppliers")
    doc.supplier_type = "Company"
    doc.insert(ignore_permissions=True)
    return doc.name


def ensure_item(item_code, item_name, item_group, uom="Nos", batch=True, expiry=True, company=None, standard_rate=100):
    if frappe.db.exists("Item", item_code):
        return item_code
    company = company or get_company()
    doc = frappe.new_doc("Item")
    doc.item_code = item_code
    doc.item_name = item_name
    doc.item_group = ensure_item_group(item_group)
    doc.stock_uom = ensure_uom(uom)
    doc.is_stock_item = 1
    doc.include_item_in_manufacturing = 0
    doc.has_batch_no = 1 if batch else 0
    doc.has_expiry_date = 1 if expiry else 0
    doc.valuation_rate = standard_rate
    doc.standard_rate = standard_rate
    if frappe.get_meta("Item").has_field("gst_hsn_code"):
        doc.gst_hsn_code = "300490"
    if frappe.get_meta("Item").has_field("pharma_brand"):
        doc.pharma_brand = item_name.split()[0]
    if frappe.get_meta("Item").has_field("pharma_composition"):
        doc.pharma_composition = item_name.split()[0] + " Composition"
    if frappe.get_meta("Item").has_field("pharma_manufacturer"):
        doc.pharma_manufacturer = "PQS Demo Pharma Ltd"
    for fld, val in {
        "pharma_mrp": standard_rate * 1.5,
        "pharma_ptr": standard_rate,
        "pharma_pts": standard_rate * 0.9,
        "pharma_ptd": standard_rate * 0.8,
    }.items():
        if frappe.get_meta("Item").has_field(fld):
            doc.set(fld, val)
    doc.append("item_defaults", {
        "company": company,
        "default_warehouse": None,
        "income_account": get_income_account(company),
        "expense_account": get_expense_account(company)
    })
    doc.insert(ignore_permissions=True)
    return doc.name


def ensure_batch(batch_id, item_code, expiry_days=365):
    if frappe.db.exists("Batch", batch_id):
        return batch_id
    b = frappe.new_doc("Batch")
    b.batch_id = batch_id
    b.item = item_code
    b.expiry_date = add_days(nowdate(), expiry_days)
    b.insert(ignore_permissions=True)
    return b.name


def ensure_opening_stock(item_code, batch_no, warehouse, qty, rate=100):
    existing = frappe.db.sql("""
        SELECT SUM(actual_qty) qty
        FROM `tabStock Ledger Entry`
        WHERE item_code=%s AND warehouse=%s AND batch_no=%s
    """, (item_code, warehouse, batch_no), as_dict=True)
    if existing and flt(existing[0].qty) >= flt(qty):
        return None

    se = frappe.new_doc("Stock Entry")
    se.stock_entry_type = "Material Receipt"
    se.posting_date = nowdate()
    se.append("items", {
        "item_code": item_code,
        "t_warehouse": warehouse,
        "qty": qty,
        "basic_rate": rate,
        "batch_no": batch_no
    })
    se.insert(ignore_permissions=True)
    se.submit()
    return se.name


def ensure_doctor(code, name, specialty, territory, sales_person, cls="A"):
    if frappe.db.exists("Pharma Doctor", code):
        return code
    d = frappe.new_doc("Pharma Doctor")
    d.doctor_code = code
    d.doctor_name = name
    d.specialty = specialty
    d.qualification = "MD"
    d.doctor_class = cls
    d.territory = territory
    d.assigned_mr = sales_person
    d.clinic_name = f"{name} Clinic"
    d.mobile_no = "9999999999"
    d.active = 1
    d.potential_value = 100000 if cls in ["A+", "A"] else 50000
    if frappe.get_meta("Pharma Doctor").has_field("current_share"):
        d.current_share = 20
    if frappe.get_meta("Pharma Doctor").has_field("target_share"):
        d.target_share = 40
    d.insert(ignore_permissions=True)
    return d.name


def create_sales_invoice(customer, company, warehouse, items):
    # idempotent demo invoice guard
    marker = f"{DEMO_PREFIX}-INV-{customer}"
    existing = frappe.db.get_value("Sales Invoice", {"po_no": marker, "docstatus": 1}, "name")
    if existing:
        return existing

    si = frappe.new_doc("Sales Invoice")
    si.customer = customer
    si.company = company
    si.posting_date = nowdate()
    si.update_stock = 1
    si.po_no = marker
    si.debit_to = get_receivable_account(company)
    for item_code, qty, rate, batch_no in items:
        si.append("items", {
            "item_code": item_code,
            "qty": qty,
            "rate": rate,
            "warehouse": warehouse,
            "batch_no": batch_no,
            "income_account": get_income_account(company)
        })
    si.insert(ignore_permissions=True)
    si.submit()
    return si.name


def seed_masters():
    company = get_company()
    abbr = get_abbr(company)
    main_wh = ensure_warehouse(f"PQS Demo Main Warehouse - {abbr}", company)
    sample_wh = ensure_warehouse(f"PQS Demo Sample Warehouse - {abbr}", company)
    returns_wh = ensure_warehouse(f"PQS Demo Returns Warehouse - {abbr}", company)

    territories = [ensure_territory(x) for x in ["PQS Mumbai West", "PQS Pune Central", "PQS Nashik North"]]

    head = ensure_sales_person("PQS Sales Head")
    rm = ensure_sales_person("PQS Regional Manager", head)
    am1 = ensure_sales_person("PQS Area Manager West", rm)
    am2 = ensure_sales_person("PQS Area Manager Pune", rm)
    mr1 = ensure_sales_person("PQS MR Ajay", am1)
    mr2 = ensure_sales_person("PQS MR Neha", am1)
    mr3 = ensure_sales_person("PQS MR Sameer", am2)

    for sp, lvl, parent, territory in [
        (head, "Sales Head", None, None),
        (rm, "Regional Manager", head, None),
        (am1, "Area Manager", rm, territories[0]),
        (am2, "Area Manager", rm, territories[1]),
        (mr1, "MR", am1, territories[0]),
        (mr2, "MR", am1, territories[2]),
        (mr3, "MR", am2, territories[1]),
    ]:
        if frappe.db.exists("DocType", "Pharma Sales Hierarchy") and not frappe.db.exists("Pharma Sales Hierarchy", sp):
            h = frappe.new_doc("Pharma Sales Hierarchy")
            h.sales_person = sp
            h.role_level = lvl
            h.reports_to = parent
            h.territory = territory
            h.active = 1
            h.insert(ignore_permissions=True)

    suppliers = [ensure_supplier("PQS Demo Contract Manufacturer"), ensure_supplier("PQS Demo Packaging Supplier")]

    products = [
        ("PQS-CARD-10", "CardioPlus 10mg Tablet", "PQS Cardiology", 120),
        ("PQS-CARD-20", "CardioPlus 20mg Tablet", "PQS Cardiology", 160),
        ("PQS-DIAB-500", "GlucoCare 500mg Tablet", "PQS Diabetes", 90),
        ("PQS-DIAB-1000", "GlucoCare 1000mg Tablet", "PQS Diabetes", 130),
        ("PQS-GASTRO", "GastroRelief Capsule", "PQS Gastro", 80),
        ("PQS-PAIN", "PainEase Tablet", "PQS Pain", 70),
        ("PQS-VITD", "VitaD3 Softgel", "PQS Vitamins", 60),
        ("PQS-IRON", "IronWell Syrup", "PQS Vitamins", 75),
        ("PQS-ABX", "SafeCef 200mg Tablet", "PQS Anti-Infective", 180),
        ("PQS-SAMPLE-CARD", "CardioPlus Physician Sample", "PQS Samples", 0),
    ]
    item_codes = []
    for code, name, group, rate in products:
        item_codes.append(ensure_item(code, name, group, company=company, standard_rate=rate))

    batches = []
    for i, code in enumerate(item_codes):
        if code == "PQS-SAMPLE-CARD":
            batch = ensure_batch(f"{code}-B01", code, 240)
            ensure_opening_stock(code, batch, sample_wh, 500, 1)
        else:
            batch1 = ensure_batch(f"{code}-B01", code, 180 + i * 10)
            batch2 = ensure_batch(f"{code}-B02", code, 360 + i * 10)
            ensure_opening_stock(code, batch1, main_wh, 200, products[i][3])
            ensure_opening_stock(code, batch2, main_wh, 300, products[i][3])
            batches.append((code, batch1, batch2, products[i][3]))

    distributors = [
        ensure_customer("PQS Anaya Distributors", territories[0]),
        ensure_customer("PQS Bharat Pharma Agency", territories[1]),
        ensure_customer("PQS Carewell Medicos", territories[2]),
        ensure_customer("PQS Dhanvantari Stockist", territories[0]),
        ensure_customer("PQS Eklavya Pharma", territories[1]),
    ]

    doctors = []
    specialties = ["Cardiology", "Diabetology", "General Physician", "Gastroenterology", "Orthopedic"]
    mrs = [mr1, mr2, mr3]
    for idx in range(1, 21):
        territory = territories[(idx - 1) % len(territories)]
        mr = mrs[(idx - 1) % len(mrs)]
        cls = ["A+", "A", "B", "C"][idx % 4]
        doctors.append(ensure_doctor(f"PQS-DOC-{idx:03d}", f"Dr Demo {idx:03d}", specialties[idx % len(specialties)], territory, mr, cls))

    return {
        "company": company,
        "warehouses": {"main": main_wh, "sample": sample_wh, "returns": returns_wh},
        "territories": territories,
        "sales_persons": {"head": head, "rm": rm, "am1": am1, "am2": am2, "mr1": mr1, "mr2": mr2, "mr3": mr3},
        "items": item_codes,
        "batches": batches,
        "distributors": distributors,
        "doctors": doctors,
        "suppliers": suppliers,
    }


def seed_billing(data):
    company = data["company"]
    wh = data["warehouses"]["main"]
    batches = data["batches"]
    distributors = data["distributors"]

    invoices = []
    for idx, customer in enumerate(distributors[:3]):
        item_rows = []
        for row in batches[idx:idx+3]:
            item_code, batch1, _batch2, rate = row
            item_rows.append((item_code, 5 + idx, rate, batch1))
        invoices.append(create_sales_invoice(customer, company, wh, item_rows))
    return invoices


def seed_sfa(data):
    mrs = [data["sales_persons"]["mr1"], data["sales_persons"]["mr2"], data["sales_persons"]["mr3"]]
    territories = data["territories"]
    doctors = data["doctors"]
    items = data["items"]
    sample_item = "PQS-SAMPLE-CARD"
    sample_wh = data["warehouses"]["sample"]

    # Tour plans
    for idx, mr in enumerate(mrs):
        name_guard = frappe.db.get_value("Pharma Tour Plan", {"sales_person": mr, "year": getdate(nowdate()).year, "month": getdate(nowdate()).strftime("%B")}, "name")
        if not name_guard:
            tp = frappe.new_doc("Pharma Tour Plan")
            tp.sales_person = mr
            tp.month = getdate(nowdate()).strftime("%B")
            tp.year = getdate(nowdate()).year
            tp.territory = territories[idx % len(territories)]
            tp.status = "Draft"
            assigned_docs = [d for d in doctors if frappe.db.get_value("Pharma Doctor", d, "assigned_mr") == mr][:5]
            for j, docname in enumerate(assigned_docs):
                tp.append("plan_lines", {
                    "visit_date": add_days(nowdate(), j),
                    "territory": territories[idx % len(territories)],
                    "doctor": docname,
                    "remarks": "Demo planned visit"
                })
            tp.insert(ignore_permissions=True)

    # Sample issue
    for mr in mrs:
        if not frappe.db.get_value("Pharma Sample Issue", {"sales_person": mr, "posting_date": nowdate()}, "name"):
            si = frappe.new_doc("Pharma Sample Issue")
            si.posting_date = nowdate()
            si.sales_person = mr
            si.source_warehouse = sample_wh
            si.status = "Draft"
            si.append("items", {"item_code": sample_item, "batch_no": f"{sample_item}-B01", "qty": 50})
            si.insert(ignore_permissions=True)
            if frappe.db.exists("Batch", f"{sample_item}-B01"):
                try:
                    create_sample_stock_entry(si.name)
                    create_sample_ledger_from_issue(si.name)
                except Exception as e:
                    log(f"Sample stock entry skipped for {si.name}: {e}")

    # DCRs
    for idx, docname in enumerate(doctors[:12]):
        mr = frappe.db.get_value("Pharma Doctor", docname, "assigned_mr")
        existing = frappe.db.get_value("Pharma DCR", {"doctor": docname, "dcr_date": nowdate(), "sales_person": mr}, "name")
        if existing:
            continue
        dcr = frappe.new_doc("Pharma DCR")
        dcr.dcr_date = nowdate()
        dcr.sales_person = mr
        dcr.territory = frappe.db.get_value("Pharma Doctor", docname, "territory")
        dcr.status = "Draft"
        dcr.doctor = docname
        dcr.visit_type = "Planned"
        dcr.visit_time = frappe.utils.now_datetime()
        dcr.order_value = 10000 + idx * 500
        dcr.doctor_feedback = "Positive response to demo product."
        dcr.competitor_feedback = "Competitor brand active."
        dcr.next_followup_date = add_days(nowdate(), 14)
        for item in items[:2]:
            dcr.append("products_promoted", {"item_code": item, "promotion_message": "Demo promotion message", "response": "Positive"})
        dcr.append("samples_given", {"item_code": sample_item, "batch_no": f"{sample_item}-B01", "qty": 2})
        dcr.insert(ignore_permissions=True)
        dcr.submit()
        dcr.db_set("status", "Submitted")
        try:
            create_sample_ledger_from_dcr(dcr.name)
        except Exception as e:
            log(f"Sample ledger from DCR skipped for {dcr.name}: {e}")

    # Secondary sales
    for idx, distributor in enumerate(data["distributors"][:3]):
        existing = frappe.db.get_value("Pharma Secondary Sales", {"distributor": distributor, "period_to": nowdate()}, "name")
        if existing:
            continue
        ss = frappe.new_doc("Pharma Secondary Sales")
        ss.posting_date = nowdate()
        ss.period_from = add_days(nowdate(), -30)
        ss.period_to = nowdate()
        ss.distributor = distributor
        ss.territory = data["territories"][idx % len(data["territories"])]
        ss.sales_person = mrs[idx % len(mrs)]
        total = 0
        for item in items[:4]:
            qty = 10 + idx
            rate = frappe.db.get_value("Item", item, "standard_rate") or 100
            amount = qty * rate
            total += amount
            ss.append("items", {"item_code": item, "qty": qty, "rate": rate, "amount": amount})
        ss.total_amount = total
        ss.insert(ignore_permissions=True)
        ss.submit()

    # Targets
    for mr in mrs:
        for target_type, amount, qty in [
            ("Primary Sales", 200000, 0),
            ("Secondary Sales", 150000, 0),
            ("Doctor Visits", 0, 20),
            ("Product Promotion", 0, 30),
        ]:
            if frappe.db.get_value("Pharma Sales Target", {"sales_person": mr, "target_type": target_type, "from_date": add_days(nowdate(), -30), "to_date": add_days(nowdate(), 30)}, "name"):
                continue
            target = frappe.new_doc("Pharma Sales Target")
            target.sales_person = mr
            target.territory = frappe.db.get_value("Pharma Sales Hierarchy", mr, "territory") if frappe.db.exists("Pharma Sales Hierarchy", mr) else None
            target.from_date = add_days(nowdate(), -30)
            target.to_date = add_days(nowdate(), 30)
            target.target_type = target_type
            target.target_amount = amount
            target.target_qty = qty
            target.insert(ignore_permissions=True)
            target.submit()

    # Performance plan
    plan_name = "PQS Demo Weighted Pharma Plan"
    if not frappe.db.exists("Pharma Performance Plan", plan_name):
        pp = frappe.new_doc("Pharma Performance Plan")
        pp.plan_name = plan_name
        pp.enabled = 1
        pp.primary_sales_weight = 40
        pp.doctor_coverage_weight = 30
        pp.secondary_sales_weight = 20
        pp.product_promotion_weight = 10
        for from_score, to_score, inc in [(0, 70, 0), (70, 80, 2), (80, 90, 4), (90, 100, 6), (100, 200, 8)]:
            pp.append("slabs", {"from_score": from_score, "to_score": to_score, "incentive_percentage": inc})
        pp.insert(ignore_permissions=True)

    for mr in mrs:
        try:
            if not frappe.db.get_value("Pharma Monthly Scorecard", {"sales_person": mr, "month": getdate(nowdate()).month, "year": getdate(nowdate()).year}, "name"):
                generate_monthly_scorecard(mr, getdate(nowdate()).month, getdate(nowdate()).year, plan_name)
        except Exception as e:
            log(f"Scorecard skipped for {mr}: {e}")

    try:
        calculate_doctor_potential_scores()
    except Exception as e:
        log(f"Doctor potential scoring skipped: {e}")


def seed_all():
    """Entry point: seed all demo data."""
    frappe.flags.in_import = True
    data = seed_masters()
    invoices = seed_billing(data)
    seed_sfa(data)
    frappe.db.commit()
    log("PQS demo seed completed.")
    return {
        "status": "success",
        "company": data["company"],
        "warehouses": data["warehouses"],
        "items": len(data["items"]),
        "doctors": len(data["doctors"]),
        "distributors": len(data["distributors"]),
        "invoices": invoices,
    }


def reset_demo_data():
    """Conservative cleanup for demo-created records.

    This does not delete core ERPNext financial/stock documents aggressively
    because submitted ledgers may exist. Use a fresh demo site for clean reset.
    """
    return {
        "message": "Use a fresh demo site for a full reset. This seed is idempotent and safe to re-run."
    }
