import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import calendar

st.set_page_config(page_title='CSE Stock Calender', layout='wide')
st.title('CSE Stock Calender (pwered by NDBS)')

if 'selected_date' not in st.session_state:
    st.session_state.selected_date = None
if 'month' not in st.session_state:
    st.session_state.month = datetime.today().month
if 'year' not in st.session_state:
    st.session_state.year = datetime.today().year

@st.cache_resource
def get_sheet():
    scope = [
        'https://www.googleapis.com/auth/spreadsheets.readonly',
        'https://www.googleapis.com/auth/drive.readonly'
             ]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    return client.open('CSE_Stock_Calender').sheet1

sheet = get_sheet()

@st.cache_data(ttl=300)
def load_data():
    data = sheet.get_all_records()
    return pd.DataFrame(data)

df = load_data()

date_cols = ['Announcement Date', 'XD Date', 'Record Date', 'Payment Date']
for col in date_cols:
    df[col] = pd.to_datetime(df[col], errors='coerce')

calender_events = []
for _, row in df.iterrows():
    basic_info = {
        'Symbol': row['Symbol'],
        'Company': row['Company'],
        'Event Type': row['Event Type'],
        'Amount': row.get('Dividend Per Share')
    }

    def add_event(event_name, event_date):
        if pd.notna(event_date):
            calender_events.append({
                **basic_info,
                'Event': event_name,
                'Date': event_date 
            })

    add_event('Announcement', row['Announcement Date'])

    if row['Event Type'] == 'Dividend':
        add_event('Ex-Dividend', row['XD Date'])
        add_event('Record Date', row['Record Date'])
        add_event('Payment Date', row['Payment Date'])

    if row['Event Type'] == 'Rights Issue':
        add_event('Ex-Rights Date', row['XD Date'])
        add_event('Record Date', row['Record Date'])

    if row['Event Type'] == 'Bonus Issue':
        add_event('Ex-Bonus Date', row['XD Date'])
        add_event('Record Date', row['Record Date'])

calender_df = pd.DataFrame(calender_events)
calender_df['Date'] = pd.to_datetime(calender_df['Date']).dt.normalize()

symbols = ['All'] + sorted(calender_df['Symbol'].unique())
selected_symbol = st.sidebar.selectbox('Filter by Symbol', symbols)
filtered_calender = (calender_df if selected_symbol == 'All' else calender_df[calender_df['Symbol'] == selected_symbol])

st.sidebar.header('Calendar Control')
st.session_state.month = st.sidebar.selectbox(
    "Select Month",
    range(1,13),
    index=st.session_state.month - 1,
    format_func = lambda x: datetime(st.session_state.year,x,1).strftime("%B")
)
month = st.session_state.month

col1, col2, col3 = st.columns([1,2,1])
with col1:
    if st.button('Previous'):
        if st.session_state.month > 1:
            st.session_state.month -= 1
with col3:
    if st.button('Next'):
        if st.session_state.month < 12:
            st.session_state.month += 1
with col2:
    st.markdown(
        f"<h3 style='text-align:center'>{datetime(st.session_state.year, st.session_state.month, 1).strftime('%B %Y')}</h3>",
        unsafe_allow_html=True
        )

available_years = sorted(calender_df['Date'].dt.year.unique())
if 'Year' not in st.session_state:
    st.session_state.year = available_years[0]
st.session_state.year = st.sidebar.selectbox(
    'Select Year',
    available_years,
    index=available_years.index(st.session_state.year)
)
year = st.session_state.year

cal = calendar.Calendar()
month_days = cal.monthdatescalendar(year, month)
today = pd.Timestamp.today().normalize()

st.session_state.month = today.month
st.session_state.year = today.year

center, right = st.columns([3,1])
with center:
    st.subheader(f"{datetime(year,month,1).strftime('%B %Y')}")

    cols = st.columns(7)
    days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
    for col,day in zip(cols,days):
        col.markdown(f'**{day}**')

    for week in month_days:
        cols = st.columns(7)
        for col,day in zip(cols,week):
            if day.month != month:
                col.markdown(' ')
                continue

            day_events = filtered_calender[filtered_calender['Date']==pd.Timestamp(day)]
            is_weekend = day.weekday() >= 5
            is_today = (day == today)
            label = f"{day.day}"

            if not day_events.empty:
                label += f"(*{len(day_events)}*)"

            if is_today:
                with col:
                    st.markdown(
                        f"""
                        <div style="
                            background-color: #ffecec;
                            border:1px solid #ff4b4b;
                            border-radius:6px;
                            padding:6px;
                            text-align:center;
                            font-weight:600;
                        ">
                            {label}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                    if st.button("Select", key=f"today-{day.isoformat()}"):
                        st.session_state.selected_date = day
            elif is_weekend:
                col.button(label, key=f"{day.isoformat()}", disabled=True)
            else:
                if col.button(label, key=f"{day.isoformat()}"):
                    st.session_state.selected_date = day

    if st.session_state.selected_date:
        st.divider()
        selected = pd.Timestamp(st.session_state.selected_date)
        st.subheader(f"Events on {selected.strftime('%d %B %Y')}")
        day_events = filtered_calender[filtered_calender['Date'] == selected]

        if day_events.empty:
            st.info('No events for the day')
        else:
            st.dataframe(day_events, use_container_width=True)

        if st.button('back to Calender'):
            st.session_state.selected_date = None

    with st.expander("View All Announcements"):
        announcement_type = st.selectbox('Filter by type', ['All'] + sorted(df['Event Type'].unique().tolist()))
        filtered_df = df if announcement_type == 'All' else df[df['Event Type'] == announcement_type]
        st.dataframe(filtered_df, use_container_width=True)

with right:
    with st.expander('Upcoming Events', expanded=False):
        upcoming = filtered_calender[
            (filtered_calender['Date'] >= today) & (filtered_calender['Date'] <= today + pd.Timedelta(days=14))
        ].sort_values('Date')

        for _, row in upcoming.iterrows():
            if st.button(
                f"{row['Symbol']} | {row['Event']} | {row['Date'].strftime('%d %b')}",
                key=f"up-{row['Symbol']} - {row['Date']}"
                ):
                st.session_state.selected_date = row['Date']
                st.session_state.month = row['Date'].month
                st.session_state.year = row['Date'].year