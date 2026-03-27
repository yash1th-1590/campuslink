# CampusLink - Smart Real-Time Event Manager

A centralized campus event management system built with Flask and MySQL, enabling seamless event scheduling, registration, and attendance tracking with real-time notifications.

##  Features

### Role-Based Access Control (RBAC)
- **Admin** – Full system control, user management, analytics dashboard
- **Faculty** – Create and manage events, mark attendance, view registrations
- **Student** – Browse events, register, cancel, receive notifications

### Core Functionality
-  **Event Management** – CRUD operations for academic, cultural, sports, and workshop events
-  **Registration System** – One-click registration with duplicate and capacity validation
-  **Attendance Tracking** – Faculty can mark attendance with real-time student notifications
-  **Smart Notifications** – Automated email and in-app alerts for registration confirmations, event reminders, and attendance updates

### Advanced Features
-  **Email Validation** – Domain verification, disposable email blocking, duplicate prevention
-  **Automated Reminders** – 24-hour pre-event alerts using background threading
-  **Secure Authentication** – Password hashing (Werkzeug), session management (Flask-Login), CSRF protection (Flask-WTF)
-  **Modern UI** – Glassmorphism design, responsive Bootstrap 5 layout, dark theme

##  Tech Stack

| Category | Technologies |
|----------|--------------|
| **Backend** | Python, Flask, SQLAlchemy, Flask-Login, Flask-WTF |
| **Database** | MySQL, PyMySQL |
| **Frontend** | HTML5, CSS3, JavaScript, Bootstrap 5, Jinja2 |
| **Authentication** | Werkzeug (password hashing), Flask-Login |
| **Validation** | WTForms, Regex, Email Domain Validation |
| **Scheduler** | Python Threading, datetime |
| **Icons** | Font Awesome 6 |
| **Version Control** | Git, GitHub |

##  Prerequisites

- Python 3.8+
- MySQL 8.0+
- Git (optional)

##  Installation

### 1. Clone the Repository
```bash
git clone https://github.com/yash1th-1590/campuslink.git
cd campuslink
