import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from typing import Dict, List, Any, Tuple
import streamlit as st
from sklearn.preprocessing import StandardScaler
from sklearn.covariance import EllipticEnvelope
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import openai
import os

class DataAnalyzer:
    def __init__(self):
        """Initialize the analyzer with OpenAI"""
        try:
            openai.api_key = os.getenv('OPENAI_API_KEY')  # Set API key directly
            self.llm_available = True
        except Exception as e:
            st.warning(f"LLM not available: {str(e)}")
            self.llm_available = False

    def generate_summary_stats(self, df: pd.DataFrame) -> Dict:
        """Generate comprehensive summary statistics"""
        summary = {
            'basic_stats': df.describe(),
            'missing_values': df.isnull().sum(),
            'data_types': df.dtypes,
            'unique_counts': df.nunique(),
        }
        
        # Add correlation matrix for numerical columns
        num_cols = df.select_dtypes(include=[np.number]).columns
        if len(num_cols) > 0:
            summary['correlation'] = df[num_cols].corr()
        
        return summary

    def detect_anomalies(self, df: pd.DataFrame) -> Dict:
        """Detect anomalies in numerical columns"""
        anomalies = {}
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        
        for col in numeric_cols:
            # Skip columns with too many missing values
            if df[col].isnull().sum() / len(df) > 0.5:
                continue
            
            # Skip columns with insufficient data
            if len(df[col].dropna()) < 10:
                continue
            
            try:
                # Reshape data for EllipticEnvelope
                X = df[col].values.reshape(-1, 1)
                
                # Standardize the data
                scaler = StandardScaler()
                X_scaled = scaler.fit_transform(X)
                
                # Detect anomalies
                outlier_detector = EllipticEnvelope(contamination=0.1, random_state=42)
                outlier_labels = outlier_detector.fit_predict(X_scaled)
                
                # Store anomaly information
                anomalies[col] = {
                    'count': sum(outlier_labels == -1),
                    'indices': np.where(outlier_labels == -1)[0],
                    'values': df[col][outlier_labels == -1].values
                }
            except Exception as e:
                print(f"Error detecting anomalies in {col}: {str(e)}")
                continue
        
        return anomalies

    def create_visualization(self, df: pd.DataFrame, question: str) -> Tuple[go.Figure, str]:
        """Create appropriate visualization based on the question"""
        question_lower = question.lower()
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        
        # If no numeric columns, return None
        if len(numeric_cols) == 0:
            return None, "No numerical data available for visualization"
        
        try:
            # Distribution-related questions
            if any(term in question_lower for term in ['distribution', 'spread', 'range']):
                if len(numeric_cols) == 1:
                    col = numeric_cols[0]
                else:
                    # Try to find the column mentioned in the question
                    col = next((col for col in numeric_cols if col.lower() in question_lower), numeric_cols[0])
                
                fig = px.histogram(
                    df, x=col,
                    title=f"Distribution of {col}",
                    template="simple_white",
                    marginal="box"  # Add a box plot on the margin
                )
                return fig, "Distribution plot with box plot"
            
            # Trend or pattern questions
            elif any(term in question_lower for term in ['trend', 'pattern', 'change']):
                if 'date' in df.columns or any('time' in col.lower() for col in df.columns):
                    time_col = next(col for col in df.columns if 'date' in col.lower() or 'time' in col.lower())
                    value_col = next(col for col in numeric_cols if col != time_col)
                    fig = px.line(
                        df, x=time_col, y=value_col,
                        title=f"{value_col} Over Time",
                        template="simple_white"
                    )
                    return fig, "Time series plot"
                else:
                    # If no time column, show the trend of the main numeric column
                    col = numeric_cols[0]
                    fig = px.line(
                        df.sort_values(col), y=col,
                        title=f"Trend of {col}",
                        template="simple_white"
                    )
                    return fig, "Trend line plot"
            
            # Correlation or relationship questions
            elif any(term in question_lower for term in ['correlation', 'relationship', 'related']):
                if len(numeric_cols) > 1:
                    corr_matrix = df[numeric_cols].corr()
                    fig = px.imshow(
                        corr_matrix,
                        title="Correlation Matrix",
                        color_continuous_scale="RdBu",
                        template="simple_white"
                    )
                    return fig, "Correlation heatmap"
                else:
                    return None, "Not enough numerical columns for correlation analysis"
            
            # Comparison questions (highest/lowest)
            elif any(term in question_lower for term in ['highest', 'lowest', 'top', 'bottom', 'maximum', 'minimum']):
                if len(numeric_cols) == 1:
                    col = numeric_cols[0]
                else:
                    # Try to find the column mentioned in the question
                    col = next((col for col in numeric_cols if col.lower() in question_lower), numeric_cols[0])
                
                # Sort and get top/bottom values
                if 'highest' in question_lower or 'top' in question_lower or 'maximum' in question_lower:
                    df_sorted = df.nlargest(10, col)
                    title = f"Top 10 Highest {col} Values"
                else:
                    df_sorted = df.nsmallest(10, col)
                    title = f"Top 10 Lowest {col} Values"
                
                fig = px.bar(
                    df_sorted, y=col,
                    title=title,
                    template="simple_white"
                )
                return fig, "Bar chart of extreme values"
            
            # Outlier questions
            elif any(term in question_lower for term in ['outlier', 'unusual', 'anomaly']):
                if len(numeric_cols) == 1:
                    col = numeric_cols[0]
                else:
                    # Try to find the column mentioned in the question
                    col = next((col for col in numeric_cols if col.lower() in question_lower), numeric_cols[0])
                
                fig = px.box(
                    df, y=col,
                    title=f"Box Plot of {col} (Showing Outliers)",
                    template="simple_white"
                )
                return fig, "Box plot showing outliers"
            
            # Default visualization for other questions
            else:
                # Create a summary visualization of the main numeric column
                col = numeric_cols[0]
                fig = px.histogram(
                    df, x=col,
                    title=f"Overview of {col}",
                    template="simple_white"
                )
                return fig, "Summary histogram"
                
        except Exception as e:
            print(f"Error creating visualization: {str(e)}")
            return None, f"Error creating visualization: {str(e)}"

    def ask_question(self, df: pd.DataFrame, question: str) -> Tuple[str, go.Figure]:
        """Answer questions about the dataset using OpenAI and create relevant visualization"""
        try:
            # Get the answer using OpenAI
            context = f"""
            Dataset Summary:
            - Total rows: {len(df)}
            - Columns: {', '.join(df.columns)}
            - Numerical statistics:\n{df.describe().to_string()}
            - Sample data:\n{df.head().to_string()}
            """

            prompt = f"""
            Based on this dataset information:
            {context}
            
            Question: {question}
            
            Provide a clear, concise answer using only the data available.
            """

            try:
                # Get response from OpenAI
                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are a data analyst assistant."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=150,
                    temperature=0.3
                )
                answer = response.choices[0].message['content']
            except Exception as e:
                # Fallback to basic analysis if OpenAI fails
                answer = self._basic_analysis(df, question)

            # Create visualization
            fig, viz_type = self.create_visualization(df, question)
            
            # Add visualization type to the answer if a visualization was created
            if fig is not None:
                answer = f"{answer}\n\n📊 {viz_type} has been created to help visualize this answer."
            
            return answer, fig

        except Exception as e:
            return f"Error analyzing data: {str(e)}", None

    def _basic_analysis(self, df: pd.DataFrame, question: str) -> str:
        """Perform basic analysis when OpenAI is not available"""
        question_lower = question.lower()
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        
        if not numeric_cols.empty:
            main_col = numeric_cols[0]
            
            if any(term in question_lower for term in ['highest', 'most', 'maximum', 'max']):
                max_val = df[main_col].max()
                return f"The highest value in {main_col} is {max_val:,.2f}"
            
            elif any(term in question_lower for term in ['lowest', 'least', 'minimum', 'min']):
                min_val = df[main_col].min()
                return f"The lowest value in {main_col} is {min_val:,.2f}"
            
            elif any(term in question_lower for term in ['average', 'mean']):
                avg_val = df[main_col].mean()
                return f"The average value of {main_col} is {avg_val:,.2f}"
            
            elif any(term in question_lower for term in ['total', 'sum']):
                total = df[main_col].sum()
                return f"The total sum of {main_col} is {total:,.2f}"
            
            else:
                return "I can answer questions about highest/lowest values, averages, and totals. Please try rephrasing your question."
        else:
            return "No numerical data found to analyze in this dataset." 