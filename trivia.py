
from __future__ import annotations

import typing as ty
from aurflux import Aurflux, AurfluxCog
from aurflux.argh import arghify, Arg, ChannelIDType
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import TOKENS
import pathlib
import pickle
import gspread
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_ID = ""

gspread.service_account()

def load_g_sheets_service():
    creds = None
    token = pathlib.Path(TOKENS.TOKENPATH)
    if token.exists():
        with token.open(mode="rb") as token_file:
            creds = pickle.load(token_file)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=8080)
        with token.open("wb") as token_file:
            pickle.dump(creds, token_file)

    return build('sheets', 'v4', credentials=creds)
    # Call the Sheets API
    # sheet = service.spreadsheets()

    # result = sheet.values().get(spreadsheetId=SAMPLE_SPREADSHEET_ID,
    #                             range=SAMPLE_RANGE_NAME).execute()
    # values = result.get('values', [])
    #
    # if not values:
    #     print('No data found.')
    # else:
    #     print('Name, Major:')
    #     for row in values:
    #         # Print columns A and E, which correspond to indices 0 and 4.
    #         print('%s, %s' % (row[0], row[4]))

def load_trivia_questions():
    service = load_g_sheets_service()
    service.get(SPREADSHEET_ID)

class Interface(AurfluxCog):
    def __init__(self, aurflux: Aurflux):
        super().__init__(aurflux)
        # self.G_SHEETS_SERVICE = load_g_sheets_service()

    def route(self):
        pass