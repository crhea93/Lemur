from dataclasses import dataclass


@dataclass
class PipelineContext:
    inputs: dict
    merge_bool: bool
    db_user: str
    db_password: str
    db_host: str
    db_name: str
    mydb: object
    mycursor: object
