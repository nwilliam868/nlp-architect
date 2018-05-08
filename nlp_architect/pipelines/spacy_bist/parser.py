# ******************************************************************************
# Copyright 2017-2018 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ******************************************************************************
"""Spacy-BIST parser main module."""
from __future__ import unicode_literals, print_function, division, \
    absolute_import

from os import path

from spacy import load as spacy_load

from nlp_architect.data.conll import ConllEntry
from nlp_architect.models.bist_parser import BISTModel
from nlp_architect.utils.core_nlp_doc import CoreNLPDoc
from nlp_architect.utils.io import download_file, unzip_file


class SpacyBISTParser(object):
    """Main class which handles parsing with Spacy-BIST parser.

    Args:
        verbose (bool, optional): Controls output verbosity.
        spacy_model (str, optional): Spacy model to use
        (see https://spacy.io/api/top-level#spacy.load).
        bist_model (str, optional): Path to a .model file to load. Defaults pre-trained model'.
    """
    dir = path.dirname(path.realpath(__file__))
    pretrained = path.join(dir, 'bist-pretrained', 'bist.model')

    def __init__(self, verbose=False, spacy_model='en', bist_model=None):
        if not bist_model:
            print("Using pre-trained BIST model.")
            download_pretrained_model()
            bist_model = SpacyBISTParser.pretrained

        if path.isfile(bist_model) and (isinstance(spacy_model, str) or path.isfile(spacy_model)):
            self.verbose = verbose
            self.bist_parser = BISTModel()
            self.bist_parser.load(bist_model if bist_model else SpacyBISTParser.pretrained)
            self.spacy_annotator = spacy_load(spacy_model)

    def to_conll(self, doc_text):
        """Converts a document to CoNLL format with spacy POS tags.

        Args:
            doc_text (str): raw document text.

        Yields:
            list of ConllEntry: The next sentence in the document in CoNLL format.
        """
        if isinstance(doc_text, str):
            for sentence in self.spacy_annotator(doc_text).sents:
                sentence_conll = [ConllEntry(0, '*root*', '*root*', 'ROOT-POS', 'ROOT-CPOS', '_',
                                             -1, 'rroot', '_', '_')]
                i_tok = 0
                for tok in sentence:
                    if self.verbose:
                        print(tok.text + '\t' + tok.tag_)

                    if not tok.is_space:
                        pos = tok.tag_
                        text = tok.text

                        if text != '-' or pos != 'HYPH':
                            pos = spacy_pos_to_ptb(pos, text)
                            token_conll = ConllEntry(i_tok + 1, text, tok.lemma_, pos, pos,
                                                     tok.ent_type_, -1, '_', '_', tok.idx)
                            sentence_conll.append(token_conll)
                            i_tok += 1

                if self.verbose:
                    print('-----------------------\ninput conll form:')
                    for entry in sentence_conll:
                        print(str(entry.id) + '\t' + entry.form + '\t' + entry.pos + '\t')
                yield sentence_conll

    def parse(self, doc_text, show_tok=True, show_doc=True):
        """Parse a raw text document.

        Args:
            doc_text (str)
            show_tok (bool, optional): Specifies whether to include token text in output.
            show_doc (bool, optional): Specifies whether to include document text in output.

        Returns:
            CoreNLPDoc: The annotated document.
        """
        if isinstance(doc_text, str) and type(show_tok) is bool and type(show_doc) is bool:
            doc_conll = self.to_conll(doc_text)
            parsed_doc = CoreNLPDoc()

            if show_doc:
                parsed_doc.doc_text = doc_text

            for sent_conll in self.bist_parser.predict_conll(doc_conll):
                parsed_sent = []
                conj_governors = {'and': set(), 'or': set()}

                for tok in sent_conll:
                    gov_id = int(tok.pred_parent_id)
                    rel = tok.pred_relation

                    if tok.form != '*root*':
                        if tok.form.lower() == 'and':
                            conj_governors['and'].add(gov_id)
                        if tok.form.lower() == 'or':
                            conj_governors['or'].add(gov_id)

                        if rel == 'conj':
                            if gov_id in conj_governors['and']:
                                rel += '_and'
                            if gov_id in conj_governors['or']:
                                rel += '_or'

                        parsed_tok = {'start': tok.misc, 'len': len(tok.form),
                                      'pos': tok.pos, 'ner': tok.feats,
                                      'lemma': tok.lemma, 'gov': gov_id - 1,
                                      'rel': rel}

                        if show_tok:
                            parsed_tok['text'] = tok.form
                        parsed_sent.append(parsed_tok)
                if parsed_sent:
                    parsed_doc.sentences.append(parsed_sent)
            return parsed_doc


def download_pretrained_model():
    """Downloads the pre-trained BIST model if non-existent."""
    if not path.isfile(path.join(SpacyBISTParser.dir, 'bist-pretrained', 'bist.model')):
        print('Downloading pre-trained BIST model...')
        download_file('https://s3-us-west-1.amazonaws.com/nervana-modelzoo/parse/',
                      'bist-pretrained.zip', path.join(SpacyBISTParser.dir, 'bist-pretrained.zip'))
        print('Unzipping...')
        unzip_file(path.join(SpacyBISTParser.dir, 'bist-pretrained.zip'),
                   outpath=SpacyBISTParser.dir)
        print('Done.')


def spacy_pos_to_ptb(pos, text):
    """Converts a Spacy part-of-speech tag to a Penn Treebank part-of-speech tag."""
    norm_pos = pos
    if text == '...':
        norm_pos = ':'
    elif text == '*':
        norm_pos = 'SYM'
    elif pos == 'AFX':
        norm_pos = 'JJ'
    elif pos == 'ADD':
        norm_pos = 'NN'
    elif text != pos and text in [',', '.', ":", '``', '-RRB-', '-LRB-']:
        norm_pos = text
    elif pos in ['NFP', 'HYPH', 'XX']:
        norm_pos = 'SYM'
    return norm_pos