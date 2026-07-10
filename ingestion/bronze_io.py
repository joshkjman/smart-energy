import pathlib

def write_bronze(key: str, body: str) -> None:
    """Write an already-serialized JSON body to Bronze at `key`.
    Local dev -> data/<key>; later swaps to boto3 put_object (SSE on, private).
    """
    path = pathlib.Path(f'data/{key}')
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f: 
        f.write(body)