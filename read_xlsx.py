import openpyxl

wb = openpyxl.load_workbook('./Eingang/jG7tJf-FI5879977991629465-hauptkonto-account-statement-debit-2026-04-01_2026-04-30.xlsx', data_only=True)
ws = wb.active

for row in ws.iter_rows(values_only=True):
    if any(row):
        print([str(cell)[:50] if cell else '' for cell in row])
