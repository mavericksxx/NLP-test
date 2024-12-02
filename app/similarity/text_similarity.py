from sklearn.feature_extraction.text import TfidfVectorizer
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from transformers import AutoTokenizer, AutoModel
import torch
import numpy as np
from collections import defaultdict
import nltk
import os
import sys

# Set NLTK data path to project directory
current_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
nltk_data_dir = os.path.join(current_dir, 'nltk_data')
os.makedirs(nltk_data_dir, exist_ok=True)

# Ensure NLTK data path is set correctly
nltk.data.path = [nltk_data_dir] + nltk.data.path

def ensure_nltk_packages():
    """Ensure all required NLTK packages are downloaded"""
    packages = {
        'punkt': 'tokenizers/punkt',
        'stopwords': 'corpora/stopwords',
        'wordnet': 'corpora/wordnet'
    }
    
    for package, path in packages.items():
        try:
            nltk.data.find(path)
            print(f"Found {package} data")
        except LookupError:
            print(f"Downloading {package}")
            try:
                nltk.download(package, download_dir=nltk_data_dir, quiet=True)
                print(f"Successfully downloaded {package}")
            except Exception as e:
                print(f"Error downloading {package}: {str(e)}")
                sys.exit(1)

# Ensure NLTK packages are available before proceeding
ensure_nltk_packages()

class SemanticAnalyzer:
    def __init__(self):
        try:
            self.tokenizer = AutoTokenizer.from_pretrained('sentence-transformers/paraphrase-MiniLM-L3-v2')
            self.model = AutoModel.from_pretrained('sentence-transformers/paraphrase-MiniLM-L3-v2')
            self.stop_words = set(stopwords.words('english'))
            self.lemmatizer = WordNetLemmatizer()
        except Exception as e:
            print(f"Error initializing SemanticAnalyzer: {str(e)}")
            raise

    def preprocess_text(self, text):
        """Preprocess text by splitting into lines"""
        try:
            # Split into lines and remove empty ones
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            return lines
        except Exception as e:
            print(f"Error in preprocess_text: {str(e)}")
            raise

    def get_embeddings(self, segments):
        """Get BERT embeddings for text segments"""
        embeddings = []
        
        for segment in segments:
            # Tokenize and get BERT embeddings
            inputs = self.tokenizer(segment, padding=True, truncation=True, return_tensors='pt')
            with torch.no_grad():
                outputs = self.model(**inputs)
            
            # Use mean pooling to get segment embedding
            attention_mask = inputs['attention_mask']
            token_embeddings = outputs.last_hidden_state
            input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
            segment_embedding = torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)
            
            embeddings.append(segment_embedding.numpy()[0])
        
        return np.array(embeddings)

    def compute_semantic_similarity(self, embeddings1, embeddings2):
        """Compute semantic similarity between two sets of embeddings"""
        similarities = []
        
        for emb1 in embeddings1:
            # Compute cosine similarity with each embedding in the second set
            sims = [np.dot(emb1, emb2)/(np.linalg.norm(emb1)*np.linalg.norm(emb2)) for emb2 in embeddings2]
            similarities.append(max(sims))  # Take best match
        
        return np.mean(similarities)

    def analyze_semantic_consistency(self, text1, text2):
        """Analyze semantic consistency between two texts"""
        # Preprocess and segment texts
        segments1 = self.preprocess_text(text1)
        segments2 = self.preprocess_text(text2)
        
        # Get embeddings
        embeddings1 = self.get_embeddings(segments1)
        embeddings2 = self.get_embeddings(segments2)
        
        # Compute overall semantic similarity
        similarity = self.compute_semantic_similarity(embeddings1, embeddings2)
        
        # Analyze internal consistency
        consistency_analysis = {
            'doc1': self.analyze_internal_consistency(segments1, embeddings1),
            'doc2': self.analyze_internal_consistency(segments2, embeddings2)
        }
        
        return similarity, consistency_analysis

    def analyze_internal_consistency(self, segments, embeddings):
        """Analyze semantic consistency within a document line by line"""
        inconsistencies = []
        
        for i in range(len(segments)-1):
            similarity = np.dot(embeddings[i], embeddings[i+1])/(np.linalg.norm(embeddings[i])*np.linalg.norm(embeddings[i+1]))
            
            # If similarity is less than 0.05 (95% different), mark as potential inconsistency
            if similarity < 0.05:  # Changed threshold from 0.03 to 0.05
                inconsistencies.append({
                    'segment_index': i,
                    'segment_text': segments[i],
                    'next_segment_text': segments[i+1],
                    'similarity_score': float(similarity),
                    'line_number': i + 1  # Add line number for reference
                })
        
        return inconsistencies

def compute_text_similarity(text1, text2):
    """
    Compute semantic similarity between two texts and analyze consistency
    """
    analyzer = SemanticAnalyzer()
    similarity, consistency_analysis = analyzer.analyze_semantic_consistency(text1, text2)
    
    return {
        'similarity_score': float(similarity),
        'consistency_analysis': consistency_analysis
    }