from dotenv import load_dotenv

from langflow.helpers.windows_postgres_helper import (
    configure_windows_postgres_event_loop,
)

# The Windows event-loop helper checks LANGFLOW_DATABASE_URL, so the environment
# must be loaded before configuring the policy. The CLI processes --env-file only
# after this bootstrap code has run.
load_dotenv(".env", override=True)
configure_windows_postgres_event_loop(source="pycharm")

from langflow.__main__ import main

if __name__ == "__main__":
    main()
