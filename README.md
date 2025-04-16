# Telegram Course Management Bot

A Telegram bot built with Python for managing educational courses with user registration and administration features.

## Features

- **User Management**
  - User registration with personal information
  - Profile management (name, surname, national ID)
  - Role-based access (Admin/User)

- **Course Management** (Admin Only)
  - Create new courses
  - Edit existing courses
  - List all courses
  - Manage course status

- **Student Features**
  - View available courses
  - Register for courses
  - View enrolled courses
  - Access certificates

## Technology Stack

- Python 3.11+
- [pyTelegramBotAPI](https://github.com/eternnoir/pyTelegramBotAPI)
- SQLAlchemy (PostgreSQL)
- Poetry for dependency management

## Getting Started

### Prerequisites

- Python 3.11 or higher
- PostgreSQL
- Poetry

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd telegram-bot
```

2. Install dependencies using Poetry:
```bash
poetry install
```

3. Set up the PostgreSQL database:
```bash
docker-compose up -d
```

4. Configure the bot:
   - Copy `.env.example` to `.env`
   - Add your Telegram Bot Token
   - Update database credentials if needed

5. Run the bot:
```bash
poetry run start
```

## Development

### Project Structure
```
telegram-bot/
├── src/
│   ├── constants/     # Constants and messages
│   ├── control/       # Flow control and keyboards
│   ├── repositories/  # Database models and CRUD
│   ├── utils/        # Utility functions
│   └── main.py       # Main bot file
├── scripts/          # Utility scripts
└── tests/           # Test files
```

### Available Commands

- `poetry run start` - Start the bot
- `poetry run cleanup` - Clean Python cache files
- `poetry run pre-start` - Run cleanup before starting

### Code Style

This project uses:
- Black for code formatting
- isort for import sorting
- flake8 for linting

Run formatting:
```bash
poetry run black .
poetry run isort .
poetry run flake8
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

MIT License

## Authors

- **Mohammad Mehdi Yadegari** - *Initial work* - [GitHub Profile](https://github.com/myadegari)