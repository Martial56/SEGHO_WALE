import csv
import io

from django.http import HttpResponse


def build_xlsx(titre, columns, rows):
    """Construit un classeur Excel stylisé et retourne son contenu binaire (bytes)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = titre[:31] or 'Rapport'

    header_fill = PatternFill(start_color='FFE0E0E0', end_color='FFE0E0E0', fill_type='solid')
    header_font = Font(color='FF1F1F1F', bold=True)
    center = Alignment(horizontal='center', vertical='center')

    for col_idx, label in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=col_idx, value=label)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center

    for row_idx, row in enumerate(rows, start=2):
        for col_idx, value in enumerate(row, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.alignment = center

    widths = [len(str(c)) for c in columns]
    for row in rows:
        for i, value in enumerate(row):
            widths[i] = max(widths[i], len(str(value)) if value is not None else 0)
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = min(max(width + 2, 12), 45)

    ws.freeze_panes = 'A2'

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def xlsx_response(filename, titre, columns, rows):
    content = build_xlsx(titre, columns, rows)
    response = HttpResponse(
        content,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}.xlsx"'
    return response, content


def build_csv(columns, rows):
    """Construit le contenu CSV (bytes, BOM UTF-8 pour Excel)."""
    buffer = io.StringIO()
    buffer.write('﻿')
    writer = csv.writer(buffer, delimiter=';')
    writer.writerow(columns)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().encode('utf-8')


def csv_response(filename, columns, rows):
    content = build_csv(columns, rows)
    response = HttpResponse(content, content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
    return response, content
