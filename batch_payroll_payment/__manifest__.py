{
    "name": "Batch Payroll Payment",
    "version": "18.0.1.0.0",
    "category": "Human Resources/Payroll",
    "summary": "Batch Payroll Payment Module - Pay Multiple Employee Payslips at Once | Odoo HR Payroll Payment Wizard | Bulk Salary Payment Processing | Automated Payroll Payment Management",
    "description": """
Batch Payroll Payment Module for Odoo
=====================================

Efficiently process multiple payroll payslips in a single batch payment action. 
This powerful Odoo module streamlines your HR and Accounting workflow by enabling 
bulk payment processing for employee salaries.

Key Benefits:
-------------
* Save time with batch payment processing
* Reduce manual data entry errors
* Streamline payroll payment workflow
* Multi-company support
* Standard Odoo payment integration

Perfect for HR managers and accountants who need to process multiple employee 
payroll payments efficiently using Odoo's standard payment register wizard.
    """,

    "author": "Rashid Ali",
    "website": "https://www.odoo.com",

    "license": "OPL-1",
    "price": 10.0,
    "currency": "USD",

    "depends": [
        "hr_payroll",
        "account"
    ],

    "data": [
        "views/batch_payment_server_action.xml",
        "views/account_payment_register_view.xml",
    ],
    
    "images": [
        "static/description/screenshots/cover.png",
        "static/description/screenshots/banner.png",
    ],
    
    "icon": "/batch_payroll_payment/static/description/cover.png",

    "installable": True,
    "application": False,
}
