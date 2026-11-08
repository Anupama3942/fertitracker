"""
Pure-Python PO-to-MO compiler.
Works without needing GNU gettext (msgfmt.exe) on Windows.
Based on standard Python Tools/i18n/msgfmt.py.
"""
import os
import struct
import glob

def generate_mo(po_path, mo_path):
    with open(po_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    messages = {}
    msgid = None
    msgstr = None
    is_msgid = False
    is_msgstr = False

    def unescape(s):
        s = s.strip()
        if s.startswith('"') and s.endswith('"'):
            s = s[1:-1]
        # Only replace standard PO escape sequences; never touch UTF-8 text!
        parts = []
        i = 0
        n = len(s)
        while i < n:
            if s[i] == '\\' and i + 1 < n:
                c = s[i + 1]
                if c == 'n':
                    parts.append('\n')
                elif c == 't':
                    parts.append('\t')
                elif c == 'r':
                    parts.append('\r')
                elif c == '"':
                    parts.append('"')
                elif c == '\\':
                    parts.append('\\')
                else:
                    parts.append('\\' + c)
                i += 2
            else:
                parts.append(s[i])
                i += 1
        return ''.join(parts)

    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('msgid '):
            if msgid is not None and msgstr is not None:
                messages[msgid] = msgstr
            msgid = unescape(line[6:])
            msgstr = ''
            is_msgid = True
            is_msgstr = False
        elif line.startswith('msgstr '):
            msgstr = unescape(line[7:])
            is_msgid = False
            is_msgstr = True
        elif line.startswith('"'):
            if is_msgid and msgid is not None:
                msgid += unescape(line)
            elif is_msgstr and msgstr is not None:
                msgstr += unescape(line)

    if msgid is not None and msgstr is not None:
        messages[msgid] = msgstr

    # Build binary .mo file
    # Sort keys
    keys = sorted(messages.keys())
    # Header format: magic (0x950412de), version (0), count (N),
    # offset of orig table, offset of trans table, hash size (0), hash offset (0)
    magic = 0x950412de
    version = 0
    count = len(keys)

    orig_table = []
    trans_table = []
    orig_strings = b''
    trans_strings = b''

    for k in keys:
        k_bytes = k.encode('utf-8')
        v_bytes = messages[k].encode('utf-8')
        orig_table.append((len(k_bytes), len(orig_strings)))
        orig_strings += k_bytes + b'\x00'
        trans_table.append((len(v_bytes), len(trans_strings)))
        trans_strings += v_bytes + b'\x00'

    # Table offsets
    header_size = 7 * 4
    orig_table_offset = header_size
    trans_table_offset = orig_table_offset + count * 8
    strings_offset = trans_table_offset + count * 8

    # Recalculate string absolute offsets
    orig_table_final = [(l, off + strings_offset) for l, off in orig_table]
    trans_offset_base = strings_offset + len(orig_strings)
    trans_table_final = [(l, off + trans_offset_base) for l, off in trans_table]

    with open(mo_path, 'wb') as f:
        # Header
        f.write(struct.pack('Iiiiiii', magic, version, count, orig_table_offset, trans_table_offset, 0, 0))
        # Orig table
        for l, off in orig_table_final:
            f.write(struct.pack('ii', l, off))
        # Trans table
        for l, off in trans_table_final:
            f.write(struct.pack('ii', l, off))
        # Orig strings
        f.write(orig_strings)
        # Trans strings
        f.write(trans_strings)

    print(f"Compiled {po_path} -> {mo_path} ({count} messages)")

def main():
    po_files = glob.glob('locale/**/django.po', recursive=True)
    if not po_files:
        print("No django.po files found in locale/ directory.")
        return
    for po in po_files:
        mo = os.path.splitext(po)[0] + '.mo'
        generate_mo(po, mo)

if __name__ == '__main__':
    main()
