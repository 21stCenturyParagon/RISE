# TMUA Guide Backend

A FastAPI backend service for the TMUA (Test of Mathematics for University Admission) practice platform. The service provides question management, user authentication, and progress tracking.

## 🚀 Features

- **Authentication System**
  - JWT-based authentication using Supabase Auth
  - User registration and login
  - Password reset functionality
  - Role-based access control

- **Question Management**
  - CRUD operations for questions
  - Excel file import support
  - Question filtering and pagination
  - Support for MathJax formatted questions

- **Database**
  - Supabase integration
  - Efficient data querying
  - Secure data access patterns

## 🛠 Tech Stack

- FastAPI
- Supabase
- Python 3.11+
- Pandas (for Excel processing)
- Loguru (for logging)

## 📋 Prerequisites

- Python 3.11 or higher
- Supabase account and project
- PostgreSQL (provided by Supabase)

## ⚙️ Environment Variables

Create a `.env` file in the root directory with the following variables:

```env
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key
```

## 🔧 Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd backend
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run the application:
```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`

## 📚 API Documentation

Once the server is running, view the interactive API documentation at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`


## 🔒 Security

- JWT token-based authentication
- Role-based access control
- Secure password handling
- Environment variable configuration
- CORS protection

## 💾 Database Schema

### TMUA Table
```sql
create table "TMUA" (
    ques_number int8 primary key,
    created_at timestamptz default now(),
    question text not null,
    options text not null,
    image text,
    solution text not null,
    topic text not null,
    difficulty text not null,
    source text not null,
    q_type int2 not null,
    correct_answer text not null,
    solution_image text
);
```

## 🧪 Running Tests

```bash
pytest
```

## 📝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request


## 🚧 Future Improvements

- [ ] Add caching layer
- [ ] Implement rate limiting
- [ ] Add more question types support
- [ ] Enhance error handling
- [ ] Add more test coverage
- [ ] Add performance monitoring
- [ ] Implement webhooks for notifications
