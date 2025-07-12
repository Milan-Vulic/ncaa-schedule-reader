import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import json
from urllib.parse import urlparse
from openai import OpenAI
from dotenv import load_dotenv

# Initialize session state for authentication
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

# Password login
if not st.session_state["authenticated"]:
    password = st.text_input("🔒 Enter access password:", type="password")
    if password == "alex":  # ⬅️ Replace with your own password
        st.session_state["authenticated"] = True
        st.success("✅ Access granted.")
        st.rerun()
    elif password:
        st.error("❌ Incorrect password")
    st.stop()

# Load OpenAI API key
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

# Setup page
st.set_page_config(layout="wide", page_title="NCAA Schedule Reader")
st.title("🏈 NCAA Schedule Reader")

# Input: multiple URLs
st.markdown("Paste one or more team schedule links (each on a new line):")
schedule_links_input = st.text_area("Schedule URLs", height=75)

if st.button("Get Schedule"):
    schedule_links = [url.strip() for url in schedule_links_input.strip().splitlines() if url.strip()]

    if not schedule_links:
        st.warning("⚠️ Please paste at least one valid NCAA schedule URL.")
    else:
        combined_df = pd.DataFrame()

        for schedule_url in schedule_links:
            try:
                # Parse team domain
                parsed_url = urlparse(schedule_url)
                team_domain = parsed_url.netloc.replace("www.", "")

                # Scrape page
                response = requests.get(schedule_url, timeout=10)
                soup = BeautifulSoup(response.text, 'html.parser')
                raw_text = soup.get_text(separator=' ', strip=True)

                # Extract opponent domains
                page_domain = parsed_url.netloc
                opponent_links = soup.find_all('a', href=True)
                domain_map = {}

                for link in opponent_links:
                    href = link['href']
                    if href.startswith("http"):
                        domain = urlparse(href).netloc.replace("www.", "")
                        name = link.get_text(strip=True)
                        if domain and name and page_domain not in domain:
                            domain_map[name.lower()] = domain

                # GPT prompt
                prompt = f"""
You are a data extraction assistant. From the text below, extract the team's sports schedule into a JSON list:

[
  {{
    "Date": "DD-MM-YYYY",
    "Time": "hh:mm (24-hour)",
    "Team Name": "Team",
    "Ground": "Home/Away/Neutral",
    "Opponent Team Name": "Opponent",
    "Venue": "Stadium",
    "Location": "City, State",
    "Conference": "Conference" or empty,
    "Promo": "Promo Name" or empty
  }},
  ...
]

Return valid JSON only. Do not wrap it in Markdown or include comments.

Text:
{raw_text}
"""

                completion = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "You clean and structure NCAA schedules into JSON format."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=2000,
                    temperature=0
                )

                json_text = completion.choices[0].message.content.strip()
                try:
                    data = json.loads(json_text)
                except json.JSONDecodeError:
                    continue

                df = pd.DataFrame(data)

                # Add opponent domain
                opponent_domains = []
                for opponent in df["Opponent Team Name"]:
                    domain = ""
                    for name_key in domain_map:
                        if name_key in opponent.lower():
                            domain = domain_map[name_key]
                            break
                    opponent_domains.append(domain)
                df["Opponent Domain"] = opponent_domains

                # Add team domain
                df["Team Domain"] = team_domain

                # Reorder columns
                desired_order = [
                    "Date", "Time", "Team Name", "Opponent Team Name",
                    "Team Domain", "Opponent Domain", "Ground",
                    "Venue", "Location", "Conference", "Promo"
                ]
                df = df[[col for col in desired_order if col in df.columns]]

                combined_df = pd.concat([combined_df, df], ignore_index=True)

            except Exception:
                continue

        # Show results
        if not combined_df.empty:
            st.session_state["full_schedule"] = combined_df
        else:
            st.error("❌ No data extracted from any URL.")

# Display table and filter
if "full_schedule" in st.session_state:
    df = st.session_state["full_schedule"]

    st.markdown("### 🎯 Filter by Ground")
    col1, col2, col3 = st.columns(3)
    with col1:
        show_home = st.toggle("Home", value=True)
    with col2:
        show_away = st.toggle("Away", value=False)
    with col3:
        show_neutral = st.toggle("Neutral", value=False)

    selected = []
    if show_home: selected.append("Home")
    if show_away: selected.append("Away")
    if show_neutral: selected.append("Neutral")

    filtered_df = df[df["Ground"].isin(selected)]

    st.dataframe(filtered_df, use_container_width=True, hide_index=True, height=None)

    csv = filtered_df.to_csv(index=False)
    st.download_button("⬇ Download CSV", csv, "combined_schedule.csv", "text/csv")
