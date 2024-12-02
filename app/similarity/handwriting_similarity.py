import requests
import io
import numpy as np
from pdf2image import convert_from_path
import os
import base64

def compute_handwriting_similarity(pdf_path1, pdf_path2):
    """
    Compute similarity between handwriting in two PDFs using Google Cloud Vision API
    """
    try:
        # Convert PDFs to images
        images1 = convert_from_path(pdf_path1)
        images2 = convert_from_path(pdf_path2)

        # Get API key
        api_key = os.environ.get('GOOGLE_CLOUD_API_KEY')
        print(f"Using Google Cloud API key: {api_key[:10]}...")

        # Get handwriting features for both documents
        features1 = extract_handwriting_features(images1, api_key)
        features2 = extract_handwriting_features(images2, api_key)

        # Add anomaly and variation detection
        anomalies1, variations1 = detect_internal_anomalies(features1)
        anomalies2, variations2 = detect_internal_anomalies(features2)

        # Compare features and calculate similarity score
        similarity, feature_scores = compare_handwriting_features(features1, features2)

        return float(np.clip(similarity, 0, 1)), feature_scores, anomalies1, anomalies2, variations1, variations2
    except Exception as e:
        print(f"Detailed error in handwriting similarity: {str(e)}")
        print(f"API key used: {api_key[:10]}...")
        raise Exception(f"Error computing handwriting similarity: {str(e)}")

def extract_handwriting_features(images, api_key):
    """
    Extract handwriting features from images using Google Cloud Vision API
    """
    features = []  # List to store features for each page
    
    for page_num, image in enumerate(images):
        page_features = []  # Features for current page
        try:
            # Convert image to bytes
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='PNG')
            img_bytes = img_byte_arr.getvalue()
            
            # Convert to base64
            img_base64 = base64.b64encode(img_bytes).decode()

            # Prepare request to Google Cloud Vision API
            url = f'https://vision.googleapis.com/v1/images:annotate?key={api_key}'
            
            payload = {
                'requests': [{
                    'image': {
                        'content': img_base64
                    },
                    'features': [{
                        'type': 'DOCUMENT_TEXT_DETECTION',
                        'maxResults': 50
                    }]
                }]
            }
            
            # Print request details for debugging
            print(f"Making request to Google Vision API...")
            print(f"URL: {url[:60]}...")  # Only print start of URL for security
            
            # Make request
            response = requests.post(url, json=payload)
            
            # Print response status and details
            print(f"Response status code: {response.status_code}")
            if response.status_code != 200:
                print(f"Error response: {response.text}")
                continue

            result = response.json()
            
            # Extract features from response
            if 'responses' in result and result['responses']:
                response_data = result['responses'][0]
                if 'fullTextAnnotation' in response_data:
                    # Success - process the text data
                    print("Successfully extracted text features")
                    text_data = response_data['fullTextAnnotation']
                    
                    for page in text_data.get('pages', []):
                        for block in page.get('blocks', []):
                            for paragraph in block.get('paragraphs', []):
                                words = paragraph.get('words', [])
                                if words:
                                    page_features.append({
                                        'confidence': paragraph.get('confidence', 0),
                                        'word_count': len(words),
                                        'symbol_density': sum(1 for word in words 
                                                           for symbol in word.get('symbols', []) 
                                                           if not symbol.get('text', '').isalnum()) / len(words) if words else 0,
                                        'line_breaks': sum(1 for word in words 
                                                         for symbol in word.get('symbols', []) 
                                                         if symbol.get('property', {}).get('detectedBreak', {}).get('type')),
                                        'average_symbol_confidence': sum(symbol.get('confidence', 0) 
                                                                      for word in words 
                                                                      for symbol in word.get('symbols', [])) / 
                                                                   sum(1 for word in words 
                                                                      for _ in word.get('symbols', []))
                                    })
                    
        except Exception as e:
            print(f"Error processing image: {str(e)}")
            continue
        
        features.append(page_features)  # Add features for this page
    
    return features

def compare_handwriting_features(features1, features2):
    """
    Compare handwriting features and return a similarity score
    """
    if not features1 or not features2 or not features1[0] or not features2[0]:
        return 0.0, {}
    
    # Flatten page features into single list for each document
    flat_features1 = [f for page_features in features1 for f in page_features]
    flat_features2 = [f for page_features in features2 for f in page_features]
    
    if not flat_features1 or not flat_features2:
        return 0.0, {}
        
    # Calculate various similarity metrics
    conf_sim = 1 - abs(np.mean([f['confidence'] for f in flat_features1]) - 
                      np.mean([f['confidence'] for f in flat_features2]))
    
    symbol_density_sim = 1 - abs(np.mean([f['symbol_density'] for f in flat_features1]) - 
                                np.mean([f['symbol_density'] for f in flat_features2]))
    
    line_break_sim = 1 - abs(np.mean([f['line_breaks'] for f in flat_features1]) - 
                            np.mean([f['line_breaks'] for f in flat_features2]))
    
    avg_conf_sim = 1 - abs(np.mean([f['average_symbol_confidence'] for f in flat_features1]) - 
                          np.mean([f['average_symbol_confidence'] for f in flat_features2]))
    
    # Store individual scores
    feature_scores = {
        'confidence_similarity': float(np.clip(conf_sim, 0, 1)),
        'symbol_density_similarity': float(np.clip(symbol_density_sim, 0, 1)),
        'line_break_similarity': float(np.clip(line_break_sim, 0, 1)),
        'average_confidence_similarity': float(np.clip(avg_conf_sim, 0, 1))
    }
    
    # Weight the different similarity metrics
    weights = {
        'confidence': 0.3,
        'symbol_density': 0.3,
        'line_breaks': 0.2,
        'avg_confidence': 0.2
    }
    
    similarity = (weights['confidence'] * conf_sim +
                 weights['symbol_density'] * symbol_density_sim +
                 weights['line_breaks'] * line_break_sim +
                 weights['avg_confidence'] * avg_conf_sim)
    
    return float(np.clip(similarity, 0, 1)), feature_scores

def detect_internal_anomalies(features):
    """
    Detect anomalies within a single document's handwriting, including page-to-page variations
    """
    anomalies = []
    page_variations = []
    
    if not features or not isinstance(features[0], list):
        return [], []
        
    # Analyze each page's features
    for page_num, page_features in enumerate(features):
        if not page_features:
            continue
            
        # Calculate baseline statistics for this page
        page_confidence_mean = np.mean([f['confidence'] for f in page_features])
        page_symbol_density_mean = np.mean([f['symbol_density'] for f in page_features])
        page_line_breaks_mean = np.mean([f['line_breaks'] for f in page_features])
        
        # Store page characteristics
        page_characteristics = {
            'page_number': page_num + 1,
            'confidence': page_confidence_mean,
            'symbol_density': page_symbol_density_mean,
            'line_breaks': page_line_breaks_mean
        }
        
        # Detect internal anomalies within the page
        page_anomalies = detect_page_anomalies(page_features, page_num)
        anomalies.extend(page_anomalies)
        
        # Store page characteristics for variation analysis
        page_variations.append(page_characteristics)
    
    # Analyze variations between pages
    if len(page_variations) > 1:
        variations = analyze_page_variations(page_variations)
        return anomalies, variations
    
    return anomalies, []

def detect_page_anomalies(features, page_num):
    """
    Detect anomalies within a single page
    """
    anomalies = []
    
    # Calculate baseline statistics
    confidence_mean = np.mean([f['confidence'] for f in features])
    confidence_std = np.std([f['confidence'] for f in features])
    
    symbol_density_mean = np.mean([f['symbol_density'] for f in features])
    symbol_density_std = np.std([f['symbol_density'] for f in features])
    
    line_breaks_mean = np.mean([f['line_breaks'] for f in features])
    line_breaks_std = np.std([f['line_breaks'] for f in features])
    
    threshold = 2.0
    
    # Check each paragraph for anomalies
    for i, feature in enumerate(features):
        anomaly = {}
        
        if abs(feature['confidence'] - confidence_mean) > threshold * confidence_std:
            anomaly['confidence'] = {
                'value': feature['confidence'],
                'mean': confidence_mean,
                'deviation': abs(feature['confidence'] - confidence_mean) / confidence_std
            }
            
        if abs(feature['symbol_density'] - symbol_density_mean) > threshold * symbol_density_std:
            anomaly['symbol_density'] = {
                'value': feature['symbol_density'],
                'mean': symbol_density_mean,
                'deviation': abs(feature['symbol_density'] - symbol_density_mean) / symbol_density_std
            }
            
        if abs(feature['line_breaks'] - line_breaks_mean) > threshold * line_breaks_std:
            anomaly['line_breaks'] = {
                'value': feature['line_breaks'],
                'mean': line_breaks_mean,
                'deviation': abs(feature['line_breaks'] - line_breaks_mean) / line_breaks_std
            }
            
        if anomaly:
            anomaly['paragraph_index'] = i
            anomaly['page_number'] = page_num + 1
            anomalies.append(anomaly)
    
    return anomalies

def analyze_page_variations(page_characteristics):
    """
    Analyze variations between pages
    """
    variations = []
    threshold = 0.15  # 15% variation threshold
    
    for i in range(1, len(page_characteristics)):
        prev_page = page_characteristics[i-1]
        curr_page = page_characteristics[i]
        
        variation = {
            'from_page': prev_page['page_number'],
            'to_page': curr_page['page_number'],
            'changes': []
        }
        
        # Check confidence variation
        conf_change = abs(curr_page['confidence'] - prev_page['confidence'])
        if conf_change > threshold:
            variation['changes'].append({
                'type': 'confidence',
                'difference': conf_change,
                'description': f"Confidence changed by {(conf_change * 100):.1f}%"
            })
            
        # Check symbol density variation
        density_change = abs(curr_page['symbol_density'] - prev_page['symbol_density'])
        if density_change > threshold:
            variation['changes'].append({
                'type': 'symbol_density',
                'difference': density_change,
                'description': f"Symbol density changed by {(density_change * 100):.1f}%"
            })
            
        # Check line breaks variation
        breaks_change = abs(curr_page['line_breaks'] - prev_page['line_breaks'])
        if breaks_change > threshold:
            variation['changes'].append({
                'type': 'line_breaks',
                'difference': breaks_change,
                'description': f"Line spacing changed by {(breaks_change * 100):.1f}%"
            })
            
        if variation['changes']:
            variations.append(variation)
    
    return variations