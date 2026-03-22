import os

from app import create_app


app = create_app()


if __name__ == "__main__":
    app_env = os.getenv("APP_ENV", "dev").lower()
    app.run(
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", "5000")),
        debug=app_env == "dev",
    )
