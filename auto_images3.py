
#!/usr/bin/env python3
"""
auto_image_links_robust.py – Streamlit Cloud / Docker version
Per-tab isolation + single “Download Results” ZIP with updated CSV containing image CDN links
Handles various CSV encodings
"""
import csv, os, time, random, streamlit as st, zipfile, io
from duckduckgo_search import DDGS
from charset_normalizer import detect

# ---------- helpers -------------------------------------------------------
def safe_filename(text: str) -> str:
    import re
    return re.sub(r'[\\/:*?"<>|]+', '_', text).strip()[:150]

def get_image_url(desc: str) -> str:
    try:
        ddgs = DDGS()
        results = ddgs.images(query=desc, max_results=5, safesearch='off', region='wt-wt')
        if not results:
            return ''
        return results[0]['image']
    except Exception as e:
        raise e

# ---------- per-tab session keys ------------------------------------------
def sess(key):
    sid = st.session_state.get("_session_id", "default")
    return f"{sid}_{key}"

# ---------- page / state --------------------------------------------------
st.set_page_config(page_title="CSV Image Link Fetcher", layout="centered")
st.title("📸 CSV Image Link Fetcher")

for k in ("csv_uploaded", "rows", "fieldnames", "zip_ready"):
    st.session_state.setdefault(sess(k), None if k != "rows" else [])

log_placeholder = st.empty()

def log(msg: str):
    st.session_state.setdefault(sess("log_buffer"), [])
    st.session_state[sess("log_buffer")].append(msg)
    log_placeholder.code("\n".join(st.session_state[sess("log_buffer")][-200:]), language="text")

def reset_app():
    for k in ("csv_uploaded", "rows", "fieldnames", "zip_ready", "log_buffer"):
        st.session_state.pop(sess(k), None)
    st.rerun()

# ---------- file upload ---------------------------------------------------
if st.session_state[sess("csv_uploaded")] is None:
    uploaded = st.file_uploader("Choose CSV file", type=["csv"], key="csv_uploader")
    if uploaded:
        try:
            # Read raw bytes
            csv_bytes = uploaded.read()
            # Detect encoding
            detected = detect(csv_bytes)
            encoding = detected.get('encoding', 'utf-8') or 'utf-8'
            log(f"Detected encoding: {encoding}")
            
            # Decode with detected encoding, handling BOM for utf-8-sig
            csv_text = csv_bytes.decode(encoding).splitlines()
            reader = csv.DictReader(csv_text)
            rows = list(reader)
            fieldnames = reader.fieldnames or []

            if "description" not in fieldnames:
                st.error("CSV must contain a 'description' column.")
            else:
                st.session_state[sess("csv_uploaded")] = uploaded.name
                st.session_state[sess("rows")] = rows
                st.session_state[sess("fieldnames")] = fieldnames
                st.rerun()
        except Exception as e:
            st.error(f"Failed to read CSV: {str(e)}")
            log(f"❌ CSV read error: {str(e)}")
else:
    st.info(f"Loaded CSV: **{st.session_state[sess('csv_uploaded')]}** "
            f"— {len(st.session_state[sess('rows')])} rows")

# ---------- processing ----------------------------------------------------
if st.session_state[sess("csv_uploaded")] and not st.session_state[sess("zip_ready")]:
    out_dir = st.text_input("Output folder (inside container)", value="/tmp/images")
    os.makedirs(out_dir, exist_ok=True)

    if st.button("Start Processing", type="primary"):
        log("🚀 Starting image link fetch…")
        progress = st.progress(0)
        rows = st.session_state[sess("rows")]
        for idx, row in enumerate(rows):
            desc = row.get("description", "").strip()
            if not desc:
                log(f"⚠️ Row {idx+1}: empty description – skipped")
                row["image"] = ""
                continue
            try:
                log(f"🔍 Row {idx+1}: searching image URL for '{desc[:60]}…'")
                image_url = get_image_url(desc)
                if image_url:
                    log(f"✅ Row {idx+1}: found URL {image_url[:60]}…")
                    row["image"] = image_url
                else:
                    log(f"⚠️ Row {idx+1}: no image URL found")
                    row["image"] = ""
                progress.progress((idx + 1) / len(rows))
                time.sleep(random.uniform(1, 3))
            except Exception as e:
                log(f"❌ Row {idx+1}: error – {e}")
                row["image"] = ""

        # build ZIP with updated CSV
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            csv_path = os.path.join(out_dir, "updated.csv")
            with open(csv_path, "w", newline='', encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=st.session_state[sess("fieldnames")]).writeheader()
                csv.DictWriter(f, fieldnames=st.session_state[sess("fieldnames")]).writerows(rows)
            zf.write(csv_path, arcname="updated.csv")
        buf.seek(0)
        st.session_state[sess("zip_ready")] = buf.getvalue()
        st.rerun()

# ---------- single download + reset --------------------------------------
if st.session_state[sess("zip_ready")]:
    st.success("Processing finished!")
    st.download_button("📁 Download Results (ZIP)",
                       st.session_state[sess("zip_ready")],
                       file_name="results.zip",
                       mime="application/zip")
    if st.button("Find New Image Links", type="secondary"):
        reset_app()

