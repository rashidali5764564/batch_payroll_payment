{
    "name": "Batch Payroll Payment",
    "version": "1.2",
    "category": "Payroll",
    "author":"Rashid Ali",
    "summary": "Batch payment for payroll payslips using standard payment wizard",
    "description": """
        This module allows HR to select multiple payslips
        and pay them in one go using Odoo standard
        account.payment.register wizard.
        Optimized for large batches.
    """,

    "depends": [
        "hr_payroll", "account"
    ],

    "data": [
        "views/batch_payment_server_action.xml",
        # "views/account_payment_register_view.xml",
    ],
    
    "icon": "/batch_payroll_payment/static/description/cover.png",

    "installable": True,
    "application": False,
    "license": "LGPL-3",

}
