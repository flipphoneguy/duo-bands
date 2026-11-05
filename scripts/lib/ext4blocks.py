# Data blocks of a file in an ext4 image, in file order. Uses the leaf extents from debugfs, so extent index blocks (which `debugfs blocks` also lists) are never returned.
import re, subprocess

def block_size(img):
    m = re.search(r'Block size:\s+(\d+)', subprocess.run(['debugfs', '-R', 'stats', img], capture_output=True, text=True).stdout)
    assert m, 'could not read block size'
    return int(m.group(1))

def data_blocks(img, path):
    out = subprocess.run(['debugfs', '-R', f'ex {path}', img], capture_output=True, text=True).stdout
    leaves = []
    for line in out.splitlines():
        m = re.match(r'\s*(\d+)/\s*(\d+)\s+\d+/\s*\d+\s+(\d+)\s+-\s+(\d+)\s+(\d+)(?:\s+-\s+(\d+))?', line)
        if not m or m.group(1) != m.group(2): continue          # keep leaf level only
        lo, hi, p0 = int(m.group(3)), int(m.group(4)), int(m.group(5))
        leaves.append((lo, [p0 + i for i in range(hi - lo + 1)]))
    blocks = [b for _, bl in sorted(leaves) for b in bl]
    assert blocks, f'no extents for {path}'
    return blocks

def write_file(img, path, data):
    bs = block_size(img)
    blocks = data_blocks(img, path)
    assert len(blocks) == (len(data) + bs - 1) // bs, path
    with open(img, 'r+b') as fh:
        for i, b in enumerate(blocks):
            fh.seek(b * bs); fh.write(data[i * bs:(i + 1) * bs])
