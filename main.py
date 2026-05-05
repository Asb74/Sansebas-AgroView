from config import setup_logging
from app.main_window import MainWindow


if __name__ == "__main__":
    setup_logging()
    app = MainWindow()
    app.mainloop()
