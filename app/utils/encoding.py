import base64

def decode_base64_content(content:str)->str:
    """
    Decode base64 encoded text content into UTF-8 text.
    """

    try:
        decoded_bytes=base64.b64decode(content)

        return decoded_bytes.decode("utf-8")
    except (ValueError,UnicodeDecodeError) as exc:
        raise ValueError(
            "Unable to decode file content as UTF-8"
        ) from exc