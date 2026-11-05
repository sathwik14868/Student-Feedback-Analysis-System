import pandas as pd
import numpy as np
import matplotlib

matplotlib.use('Agg')

import matplotlib.pyplot as plt
from database import get_connection
import os


def analyze_feedback():

    conn = get_connection()

    query = """
        SELECT
            s.submission_id,
            c.course_name,
            f.rating
        FROM feedback f
        JOIN feedback_submissions s
            ON f.submission_id = s.submission_id
        JOIN courses c
            ON s.course_id = c.course_id
    """

    df = pd.read_sql(query, conn)

    total_query = "SELECT COUNT(*) FROM feedback_submissions"
    total_submissions = pd.read_sql(total_query, conn).iloc[0, 0]

    conn.close()

    if df.empty:
        return None

    # Calculate overall average rating
    overall_average = np.mean(df['rating'])

    # Calculate course-wise average ratings
    course_analysis = df.groupby('course_name')['rating'].agg(
        ['mean', 'count']
    ).reset_index()

    # Create charts folder if it doesn't exist
    os.makedirs('static', exist_ok=True)

    # Course-wise average rating chart
    plt.figure(figsize=(8, 5))

    plt.bar(
        course_analysis['course_name'],
        course_analysis['mean']
    )

    plt.title('Course-wise Average Ratings')
    plt.xlabel('Courses')
    plt.ylabel('Average Rating')
    plt.ylim(0, 5)
    plt.xticks(rotation=20)
    plt.tight_layout()

    plt.savefig('static/course_chart.png')
    plt.close()

    # Rating distribution chart
    plt.figure(figsize=(7, 5))

    rating_counts = df['rating'].value_counts().sort_index()

    plt.bar(
        rating_counts.index.astype(str),
        rating_counts.values
    )

    plt.title('Rating Distribution')
    plt.xlabel('Rating (1 to 5)')
    plt.ylabel('Number of Answers')
    plt.tight_layout()

    plt.savefig('static/rating_chart.png')
    plt.close()

    return {
        'total_submissions': total_submissions,
        'overall_average': overall_average,
        'course_analysis': course_analysis,
        'total_ratings': len(df)
    }