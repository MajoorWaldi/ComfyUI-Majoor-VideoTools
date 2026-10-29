"""Conservative interpretation of a local vision model's empty-location assessment."""
import json


def parse_plate_assessment(text: str) -> dict:
    raw=str(text).strip()
    if raw.startswith('```'):
        raw='\n'.join(raw.splitlines()[1:-1]).strip()
    try:
        data=json.loads(raw)
    except (ValueError,TypeError):
        return {'status':'uncertain','reason':'The location assessment could not be read'}
    if not isinstance(data,dict) or data.get('status') not in ('clear','person','uncertain') or not isinstance(data.get('reason'),str) or not data['reason'].strip():
        return {'status':'uncertain','reason':'The location assessment is incomplete'}
    return {'status':data['status'],'reason':data['reason'].strip()}
