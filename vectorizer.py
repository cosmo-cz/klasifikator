from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
from gensim.models.doc2vec import Doc2Vec, TaggedDocument
import pickle
from pathlib import Path


class Vectorizer():
    def __init__(self, vectorizer='tfidf', ngram=1, vocabulary=None, load_vec=None):
        if load_vec is not None:
            with open(load_vec, "wb") as file:
                self.vectorizer = pickle.load(file)
            return
        if vectorizer == 'tfidf':
            self.vectorizer = TfidfVectorizer(vocabulary=vocabulary, ngram_range=(1, ngram))
        elif vectorizer == 'bow':
            self.vectorizer = CountVectorizer(vocabulary=vocabulary, ngram_range=(1, ngram))
        else:
            raise Exception("Unknown vectorizer")

    def get_matirx(self, data):
        matrix = self.vectorizer.fit_transform(data['text'])
        return matrix

    def save(self, path):
        vec_path = str(Path(path) / "vectorizer.pickle")
        with open(vec_path, "wb") as file:
            pickle.dump(self.vectorizer, file)


class D2VVectorizer():
    def __init__(self, data=None, model=None):
        if data is None and model is None:
            raise Exception("No data or model for D2VVectorizer") # TODO po natrenovani dat default model
        if model is not None:
            if isinstance(model, str):
                self.model = Doc2Vec.load(model)
            else:
                self.model = model
            return
        if data is not None:
            documents = [TaggedDocument(doc, [i]) for i, doc in enumerate(data)]
            self.model = Doc2Vec(documents, vector_size=5, window=2, min_count=1, workers=4)
            self.model.delete_temporary_training_data(keep_doctags_vectors=True, keep_inference=True)

    def save_model(self, path):
        self.model.save(path)

    def get_vector(self, text):
        return self.model.infer_vector(text)
