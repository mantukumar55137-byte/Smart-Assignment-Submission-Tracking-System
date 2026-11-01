# Assignment Submission Tracking System

A desktop application for assignment submission, deadline tracking, versioned resubmission, rubric-based grading and performance reports.
Built with Python, Tkinter (ttk) and SQLite.

## Folder structure

```
Assignment_Submission_Tracking_System/
├── assignment_tracker_with_teacher_logout.py   # Main application (run this file)
├── requirements.txt                            # Optional packages
├── README.md                                   # This file
├── uploads/                                    # Student submissions (auto-filled)
├── exports/                                    # CSV / PDF reports and backups
├── profile_pics/                               # User profile photos
├── docs/                                       # Put your project report here
└── assignment_system.db                        # Created automatically on first run
```

## How to run

1. Install Python 3.8 or later (tick "Add Python to PATH" on Windows).
2. Optional, for charts, profile photos and PDF reports:
   `pip install -r requirements.txt`
3. Open a terminal in this folder and run:
   `python assignment_tracker_with_teacher_logout.py`

The database, folders and demo data are created automatically on first run.

## Demo accounts

| Role    | Email               | Password    |
|---------|---------------------|-------------|
| Student | student@gmail.com   | Student@123 |
| Teacher | teacher@gmail.com   | Teacher@123 |
| Admin   | admin@gmail.com     | Admin@123   |

## Main features

- Student: view assignments, submit files, late/resubmission requests, version history, marks and feedback, performance chart, CSV/PDF export
- Teacher: create/edit/delete assignments (own subject), review with rubric (Worksheet 8 + Viva 10 + Implementation 12 = 30), approve requests and students, class performance
- Admin: manage users, approvals, password reset, statistics, database backup/restore, activity log
- Security: PBKDF2 password hashing, password rules, approval workflow, audit log

## Technologies

Python 3, Tkinter/ttk, SQLite, matplotlib (optional), Pillow (optional), ReportLab (optional)
