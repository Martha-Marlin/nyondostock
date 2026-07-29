# NyondoStock — Inventory & Sales Management System

A full-stack Django web application built for a real hardware business to manage inventory, sales, credit, and deposits — from initial build through live production deployment.

**Live demo:** [nyondostock.up.railway.app](https://nyondostock.up.railway.app)

## Overview

NyondoStock replaces manual, paper-based inventory tracking with a role-based web system covering the full sales and stock workflow — built as a capstone project during my Software Engineering with Python certificate at Refactory Academy, and now in active use by the business it was built for.

## Features

- **Three role-based dashboards** — Store Manager, Sales Attendant, and Accounts Admin each see only what their role needs
- **Supplier credit tracking** — record and monitor credit owed to suppliers
- **Customer deposit scheme** — track customer deposits against future purchases
- **Sales & receipts** — process sales with automatic receipt generation and print-ready CSS
- **Form validation** — Django validation across all data-entry forms to prevent bad records
- **Custom admin panel** — Jazzmin-powered admin interface for easier back-office management
- **Custom 404 page** and polished landing page

## Tech stack

Python · Django · PostgreSQL · Railway (deployment) · Jazzmin (admin UI)

## Getting started locally

```bash
# Clone the repo
git clone https://github.com/MarthaMuronji/nyondostock.git
cd nyondostock

# Set up a virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env  # then fill in your own values

# Run migrations
python manage.py migrate

# Start the development server
python manage.py runserver
```

## Screenshots

*(Add 2–3 screenshots here — dashboard view, a sales/receipt screen, and the admin panel work well)*

## About this project

Built and deployed as a capstone for Refactory Academy's Software Engineering with Python program, then taken further into real production use for the business it serves.
