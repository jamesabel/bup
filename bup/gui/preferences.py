from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, String
import appdirs
from tobool import to_bool
from balsa import get_logger

from bup import __application_name__, __author__


log = get_logger(__application_name__)

SQLAlchemyDeclarativeBase = declarative_base()


class PreferencesTable(SQLAlchemyDeclarativeBase):
    __tablename__ = "preferences"
    key = Column(String, primary_key=True)
    value = Column(String, nullable=True)


class GUIPreferences:
    def __init__(self):

        # derive SQLite path
        self.preferences_path = Path(appdirs.user_config_dir(__application_name__, __author__), f"{__application_name__}_pref.sqlite")
        self.preferences_path.parent.mkdir(parents=True, exist_ok=True)
        self.sqlite_path = f"sqlite:///{self.preferences_path}"
        log.info(f"preferences sqlite_path path : {self.sqlite_path}")

        self.create_db()  # in case the DB does not already exist

    def create_db(self):
        # create the DB and tables if does not already exist
        engine = create_engine(self.sqlite_path)
        SQLAlchemyDeclarativeBase.metadata.create_all(engine)

    def _make_session(self):
        engine = create_engine(self.sqlite_path)
        session = sessionmaker(bind=engine)()
        return session

    def _close_session(self, session):
        log.debug("closing session")
        session.close()

    def _set(self, key: str, value):
        log.info(f"_set {key}={value}")
        session = self._make_session()

        try:
            # modify existing value
            query_result = session.query(PreferencesTable).filter_by(key=key)
            first = query_result.first()
            if first is not None:
                first.value = value
                value = None
                log.debug(f"modifying existing entry {key}={value}")
        except NoResultFound:
            log.debug(f"{key} : no result found")
        if value is not None:
            # key not already in table - add it
            pref = PreferencesTable(key=key, value=str(value))
            session.add(pref)
            log.debug(f"adding new entry {key}={value}")

        session.commit()
        self._close_session(session)
        log.debug(f"_set {key} complete")

    def _get(self, key: str, default=None):
        log.debug(f"_get {key} (default:{default})")
        session = self._make_session()
        query_result = session.query(PreferencesTable).filter_by(key=key)
        try:
            value = query_result.one().value
        except NoResultFound:
            value = default
        log.debug(f"_get : {key}={value}")
        self._close_session(session)
        return value

    def set_windows_dimensions(self, width: int, height: int):
        self._set("width", width)
        self._set("height", height)

    def get_windows_dimensions(self):
        w = int(self._get("width"))
        h = int(self._get("height"))
        log.info("w : %d , h : %d" % (w, h))
        return w, h

    # backup directory
    backup_directory_string = "backup_directory"

    def set_backup_directory(self, value: Path):
        self._set(self.backup_directory_string, str(value))

    def get_backup_directory(self) -> (Path, None):
        return self._get(self.backup_directory_string, None)

    # exclusions
    def get_exclusions_string(self, exclusion_type: str):
        return f"exclusions_{exclusion_type}"

    def set_exclusions(self, exclusion_type: str, values_string: str):
        # store as newline separated
        self._set(self.get_exclusions_string(exclusion_type), "\n".join(values_string.split()))

    def get_exclusions(self, exclusion_type: str) -> list:
        # return as a list
        return self._get(self.get_exclusions_string(exclusion_type), "").split()

    # AWS IAM (need either AWS Profile or Access Key ID/Secret Access Key pair)
    aws_profile_string = "aws_profile"

    def set_aws_profile(self, profile: str):
        self._set(self.aws_profile_string, profile)

    def get_aws_profile(self) -> str:
        return self._get(self.aws_profile_string)

    aws_access_key_id_string = "aws_access_key_id"

    def set_aws_access_key_id(self, profile: str):
        self._set(self.aws_access_key_id_string, profile)

    def get_aws_access_key_id(self) -> str:
        return self._get(self.aws_access_key_id_string)

    aws_secret_access_key_string = "aws_secret_access_key"

    def set_aws_secret_access_key(self, profile: str):
        self._set(self.aws_secret_access_key_string, profile)

    def get_aws_secret_access_key(self) -> str:
        return self._get(self.aws_secret_access_key_string)

    # dry run
    dry_run_string = "dry_run"

    def set_dry_run(self, dry_run: bool):
        self._set(self.dry_run_string, dry_run)

    def get_dry_run(self) -> bool:
        return to_bool(self._get(self.dry_run_string))
