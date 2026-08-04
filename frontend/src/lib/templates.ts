export interface Template {
  id: string;
  slug: string;
  badge: string;
  iconBg: string;
  iconColor: string;
  name: string;
  desc: string;
  tags: string[];
  code: string;
  requirements: string;
}

export const templates: Template[] = [
  {
    id: 'blank',
    slug: 'new-app',
    badge: 'PY',
    iconBg: 'var(--surface-3)',
    iconColor: 'var(--text-2)',
    name: 'Blank app',
    desc: 'A minimal starting point with a title and some text — a clean start.',
    tags: ['streamlit'],
    code: 'import streamlit as st\n\nst.set_page_config(layout="wide")\nst.title("New Streamlit app")\nst.write("Start building here.")',
    requirements: 'streamlit==1.36.0',
  },
  {
    id: 'kpi',
    slug: 'kpi-dashboard',
    badge: 'KPI',
    iconBg: 'var(--accent-soft)',
    iconColor: 'var(--text)',
    name: 'KPI dashboard',
    desc: 'Key metrics in a row of cards, plus a couple of charts.',
    tags: ['plotly', 'pandas'],
    code: 'import streamlit as st\nimport pandas as pd\nimport plotly.express as px\n\nst.set_page_config(layout="wide")\nst.title("KPI dashboard")\ncol1, col2, col3 = st.columns(3)\ncol1.metric("Revenue", "1.2M", "+8%")\ncol2.metric("Orders", "342", "+12%")\ncol3.metric("Conversion", "4.5%", "-0.2%")\ndf = pd.DataFrame({"x": range(10), "y": [i**2 for i in range(10)]})\nfig = px.line(df, x="x", y="y")\nst.plotly_chart(fig, use_container_width=True)',
    requirements: 'streamlit==1.36.0\npandas==2.2.2\nplotly==5.22.0',
  },
  {
    id: 'csv',
    slug: 'csv-viewer',
    badge: 'CSV',
    iconBg: 'var(--ok-bg)',
    iconColor: 'var(--ok-fg)',
    name: 'CSV viewer',
    desc: 'Upload a CSV and filter the table.',
    tags: ['pandas', 'upload'],
    code: 'import streamlit as st\nimport pandas as pd\n\nst.title("CSV viewer")\nuploaded = st.file_uploader("Upload a CSV", type="csv")\nif uploaded is not None:\n    df = pd.read_csv(uploaded)\n    st.dataframe(df, use_container_width=True)',
    requirements: 'streamlit==1.36.0\npandas==2.2.2',
  },
  {
    id: 'ml',
    slug: 'ml-regression',
    badge: 'ML',
    iconBg: '#efeafc',
    iconColor: '#7c3aed',
    name: 'ML regression',
    desc: 'A simple pipeline: synthetic data, LinearRegression training, and a plot of the predictions.',
    tags: ['scikit-learn', 'matplotlib'],
    code: 'import streamlit as st\nimport numpy as np\nimport matplotlib.pyplot as plt\nfrom sklearn.datasets import make_regression\nfrom sklearn.linear_model import LinearRegression\nfrom sklearn.model_selection import train_test_split\nfrom sklearn.metrics import mean_squared_error\n\nst.set_page_config(layout="wide")\nst.title("ML regression")\n\nn_samples = st.slider("Number of samples", 50, 1000, 200)\nnoise = st.slider("Noise", 0.0, 50.0, 10.0)\n\nX, y = make_regression(n_samples=n_samples, n_features=1, noise=noise, random_state=42)\nX_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)\n\nmodel = LinearRegression()\nmodel.fit(X_train, y_train)\ny_pred = model.predict(X_test)\n\ncol1, col2 = st.columns(2)\ncol1.metric("MSE", f"{mean_squared_error(y_test, y_pred):.2f}")\ncol2.metric("R²", f"{model.score(X_test, y_test):.2f}")\n\nfig, ax = plt.subplots()\nax.scatter(X_test, y_test, label="Actual")\nax.plot(X_test, y_pred, color="red", label="Predicted")\nax.legend()\nst.pyplot(fig)',
    requirements: 'streamlit==1.36.0\nnumpy==1.26.4\nscikit-learn==1.5.0\nmatplotlib==3.9.0',
  },
  {
    id: 'map',
    slug: 'map-viewer',
    badge: 'MAP',
    iconBg: '#e3f3f1',
    iconColor: '#0f7c70',
    name: 'Map',
    desc: 'An interactive folium map with markers for points of interest.',
    tags: ['folium', 'map'],
    code: 'import streamlit as st\nimport folium\nfrom streamlit_folium import st_folium\n\nst.set_page_config(layout="wide")\nst.title("Map")\n\ncenter = [51.5074, -0.1278]\nm = folium.Map(location=center, zoom_start=12)\nfolium.Marker(center, tooltip="London").add_to(m)\nfolium.Marker([51.5194, -0.1270], tooltip="Second point").add_to(m)\n\nst_folium(m, width=1200, height=600)',
    requirements: 'streamlit==1.36.0\nfolium==0.17.0\nstreamlit-folium==0.21.1',
  },
  {
    id: 'qa',
    slug: 'faq-bot',
    badge: 'QA',
    iconBg: 'var(--warn-bg)',
    iconColor: 'var(--warn-fg)',
    name: 'FAQ bot',
    desc: 'A simple text QA interface with canned answers.',
    tags: ['nlp', 'chat'],
    code: 'import streamlit as st\n\nst.title("FAQ bot")\n\nfaq = {\n    "how do i start an app?": "Press ▶ Start in the app registry.",\n    "how do i stop it?": "Press ⏹ Stop on the app card.",\n    "what is the quota?": "At most 5 simultaneously running apps per user.",\n}\n\nquestion = st.text_input("Your question")\nif question:\n    answer = faq.get(question.lower().strip())\n    if answer:\n        st.success(answer)\n    else:\n        st.warning("No answer found — try rephrasing.")',
    requirements: 'streamlit==1.36.0',
  },
];
