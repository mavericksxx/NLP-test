from flask import Blueprint, render_template, request, jsonify, current_app
from werkzeug.utils import secure_filename
import os
from app.similarity.text_similarity import compute_text_similarity
from app.similarity.handwriting_similarity import compute_handwriting_similarity
from app.utils.pdf_processor import extract_text_from_pdf, validate_pdf
from app.utils.report_generator import generate_report

main = Blueprint('main', __name__)

ALLOWED_EXTENSIONS = {'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@main.route('/')
def index():
    return render_template('index.html')

@main.route('/compare', methods=['POST'])
def compare_pdfs():
    if 'file1' not in request.files or 'file2' not in request.files:
        return jsonify({'error': 'Two PDF files are required'}), 400

    file1 = request.files['file1']
    file2 = request.files['file2']
    
    print(f"Received files: {file1.filename} and {file2.filename}")

    # Validate files
    if not all(allowed_file(f.filename) for f in [file1, file2]):
        return jsonify({'error': 'Invalid file format. Only PDF files are allowed'}), 400

    try:
        # Create upload directory if it doesn't exist
        if not os.path.exists(current_app.config['UPLOAD_FOLDER']):
            os.makedirs(current_app.config['UPLOAD_FOLDER'])

        # Save files
        filename1 = secure_filename(file1.filename)
        filename2 = secure_filename(file2.filename)
        
        filepath1 = os.path.join(current_app.config['UPLOAD_FOLDER'], filename1)
        filepath2 = os.path.join(current_app.config['UPLOAD_FOLDER'], filename2)
        
        file1.save(filepath1)
        file2.save(filepath2)
        print(f"Files saved to {filepath1} and {filepath2}")

        # Basic file validation
        if not os.path.exists(filepath1) or not os.path.exists(filepath2):
            return jsonify({'error': 'Error saving files'}), 500

        if os.path.getsize(filepath1) == 0 or os.path.getsize(filepath2) == 0:
            return jsonify({'error': 'One or both files are empty'}), 400

        # Validate PDFs
        if not validate_pdf(filepath1) or not validate_pdf(filepath2):
            return jsonify({'error': 'Invalid or corrupted PDF file(s)'}), 400

        # Extract text using Mathpix
        text1 = extract_text_from_pdf(filepath1)
        text2 = extract_text_from_pdf(filepath2)
        
        if not text1 or not text2:
            return jsonify({'error': 'Could not extract text from one or both files'}), 400

        # Calculate similarities
        text_analysis = compute_text_similarity(text1, text2)
        text_similarity = text_analysis['similarity_score']
        handwriting_similarity, feature_scores, anomalies1, anomalies2, variations1, variations2 = compute_handwriting_similarity(filepath1, filepath2)

        # Calculate weighted similarity index
        weight_text = float(request.form.get('weight_text', 0.5))
        weight_handwriting = 1 - weight_text
        
        similarity_index = (weight_text * text_similarity + 
                          weight_handwriting * handwriting_similarity)

        # Generate report with feature scores and anomalies
        report_path = generate_report(
            text_similarity, 
            handwriting_similarity, 
            similarity_index, 
            text1, 
            text2,
            feature_scores,
            anomalies1,
            anomalies2,
            variations1,
            variations2
        )

        return jsonify({
            'text_similarity': text_similarity,
            'text_consistency': text_analysis['consistency_analysis'],
            'handwriting_similarity': handwriting_similarity,
            'similarity_index': similarity_index,
            'feature_scores': feature_scores,
            'anomalies': {
                'document1': anomalies1,
                'document2': anomalies2
            },
            'variations': {
                'document1': variations1,
                'document2': variations2
            },
            'report_url': report_path
        })

    except Exception as e:
        print(f"Error in compare_pdfs: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        # Clean up uploaded files
        for filepath in [filepath1, filepath2]:
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception as e:
                print(f"Error removing file {filepath}: {str(e)}") 