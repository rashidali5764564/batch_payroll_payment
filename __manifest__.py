{
    "name": "Batch Payroll Payment",
    "version": "18.0.1.0.0",
    "category": "Human Resources/Payroll",
    "summary": "Batch payment of payroll payslips using Odoo payment wizard",

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

    "installable": True,
    "application": False,
}
