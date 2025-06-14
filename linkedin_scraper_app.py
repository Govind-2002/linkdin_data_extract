import streamlit as st
import pandas as pd
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager
import base64

# Set page config
st.set_page_config(
    page_title="LinkedIn Employee Scraper",
    page_icon="🔍",
    layout="wide"
)

# Custom CSS
st.markdown("""
    <style>
    .main {
        padding: 2rem;
    }
    .stButton>button {
        width: 100%;
    }
    .stProgress .st-bo {
        background-color: #4CAF50;
    }
    </style>
    """, unsafe_allow_html=True)

def setup_driver():
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument('--headless')  # Run in headless mode

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

def login_linkedin(driver, email, password):
    driver.get("https://www.linkedin.com/login")
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "username"))).send_keys(email)
        driver.find_element(By.ID, "password").send_keys(password)
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.XPATH, "//input[contains(@placeholder, 'Search')]")))
        return True
    except Exception as e:
        st.error(f"Login failed: {str(e)}")
        return False

def search_company(driver, company_name):
    try:
        search_box = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//input[contains(@placeholder, 'Search')]")))
        search_box.clear()
        search_box.send_keys(company_name)
        time.sleep(2)
        search_box.send_keys(u'\ue007')
        WebDriverWait(driver, 10).until(EC.url_contains("/search/"))
        return True
    except Exception as e:
        st.error(f"Search failed: {str(e)}")
        return False

def open_company_page(driver, company_name):
    try:
        xpath_expr = f"//span[text()='{company_name}']/ancestor::a[contains(@href, '/company/')]"
        company_link = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, xpath_expr)))
        driver.execute_script("arguments[0].click();", company_link)
        WebDriverWait(driver, 15).until(EC.url_contains("/company/"))
        return True
    except Exception as e:
        st.error(f"Failed to open company page: {str(e)}")
        return False

def open_people_section(driver):
    try:
        xpath_candidates = [
            "//a[contains(@href, '/people/')]",
            "//a[contains(text(), 'People') and contains(@href, '/people/')]",
            "//a[span[contains(text(),'People')]]"
        ]

        people_tab = None
        for xpath in xpath_candidates:
            try:
                people_tab = WebDriverWait(driver, 15).until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
                if people_tab:
                    break
            except TimeoutException:
                continue

        if not people_tab:
            raise Exception("People tab not found")

        driver.execute_script("arguments[0].click();", people_tab)
        WebDriverWait(driver, 15).until(EC.url_contains("/people"))
        return True
    except Exception as e:
        st.error(f"Failed to open people section: {str(e)}")
        return False

def scrape_employee_profiles(driver, max_profiles):
    employee_data = []
    scraped_urls = set()
    scroll_pause_time = 2
    last_height = driver.execute_script("return document.body.scrollHeight")
    
    progress_bar = st.progress(0)
    status_text = st.empty()

    while len(employee_data) < max_profiles:
        try:
            profile_list_items_xpath = "//li[contains(@class, 'list-style-none')]"
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, profile_list_items_xpath)))
            profiles = driver.find_elements(By.XPATH, profile_list_items_xpath)

            for profile_element in profiles:
                if len(employee_data) >= max_profiles:
                    break

                try:
                    profile_link_element = profile_element.find_element(By.XPATH, ".//a[contains(@href, '/in/')]")
                    profile_url = profile_link_element.get_attribute("href")

                    if profile_url in scraped_urls:
                        continue

                    scraped_urls.add(profile_url)

                    try:
                        name = profile_element.find_element(By.XPATH, ".//span[@aria-hidden='true' and not(ancestor::a[contains(@href, '/school/')])]").text.strip()
                    except NoSuchElementException:
                        name = "N/A"

                    try:
                        role = profile_element.find_element(By.XPATH, ".//div[contains(@class, 'entity-result__primary-subtitle')]").text.strip()
                    except NoSuchElementException:
                        role = "N/A"

                    employee_data.append({"name": name, "role": role, "url": profile_url})
                    
                    # Update progress
                    progress = min(len(employee_data) / max_profiles, 1.0)
                    progress_bar.progress(progress)
                    status_text.text(f"Scraped {len(employee_data)}/{max_profiles} profiles")

                except Exception as e:
                    continue

            if len(employee_data) >= max_profiles:
                break

            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(scroll_pause_time)

            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

        except Exception as e:
            st.error(f"Error during scraping: {str(e)}")
            break

    progress_bar.empty()
    status_text.empty()
    return employee_data

def get_download_link(df, filename, text):
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'data:file/csv;base64,{b64}'
    return f'<a href="{href}" download="{filename}">{text}</a>'

def main():
    st.title("LinkedIn Employee Scraper 🔍")
    st.markdown("---")

    # Input fields
    col1, col2 = st.columns(2)
    with col1:
        company_name = st.text_input("Company Name", placeholder="Enter company name (e.g., Google)")
    with col2:
        num_employees = st.number_input("Number of Employees to Scrape", min_value=1, max_value=100, value=10)

    # LinkedIn credentials
    st.markdown("### LinkedIn Credentials")
    col3, col4 = st.columns(2)
    with col3:
        email = st.text_input("LinkedIn Email", type="password")
    with col4:
        password = st.text_input("LinkedIn Password", type="password")

    if st.button("Start Scraping", type="primary"):
        if not all([company_name, num_employees, email, password]):
            st.error("Please fill in all fields")
            return

        with st.spinner("Initializing scraper..."):
            driver = setup_driver()

        try:
            # Login
            with st.spinner("Logging in to LinkedIn..."):
                if not login_linkedin(driver, email, password):
                    return

            # Search company
            with st.spinner(f"Searching for {company_name}..."):
                if not search_company(driver, company_name):
                    return

            # Open company page
            with st.spinner("Opening company page..."):
                if not open_company_page(driver, company_name):
                    return

            # Open people section
            with st.spinner("Navigating to People section..."):
                if not open_people_section(driver):
                    return

            # Scrape profiles
            with st.spinner("Scraping employee profiles..."):
                employees = scrape_employee_profiles(driver, num_employees)

            if employees:
                # Create DataFrame
                df = pd.DataFrame(employees)
                
                # Display results
                st.markdown("### Scraped Employee Data")
                st.dataframe(df)
                
                # Download button
                st.markdown(get_download_link(df, f"{company_name}_employees.csv", "Download CSV"), unsafe_allow_html=True)
                
                st.success(f"Successfully scraped {len(employees)} profiles!")
            else:
                st.warning("No employee data was scraped.")

        except Exception as e:
            st.error(f"An error occurred: {str(e)}")
        
        finally:
            driver.quit()

if __name__ == "__main__":
    main() 