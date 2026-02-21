import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

def line_chart(df: pd.DataFrame, y: str, title: str):
    fig, ax = plt.subplots()
    df[y].plot(ax=ax)
    ax.set_title(title)
    ax.set_xlabel("Date")
    ax.set_ylabel(y)
    st.pyplot(fig)
