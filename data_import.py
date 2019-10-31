# coding=utf-8
import xmltodict
import xml.etree.ElementTree as etree
from elasticsearch import Elasticsearch
from elasticsearch import exceptions
from elasticsearch_dsl import Search, Q
from elasticsearch_dsl.utils import AttrDict
import os
import tarfile
from helper.helper import Helper
from helper.text_extractor import TextExtractor, TextExtractorPre
from pathlib import Path
import re
import time
from preprocessor import Preprocessor


class DataImporter:

    # premiestni nazvy poli marc zaznamov z value do key casti dictionary
    # zmeni "datafield": {"@tag": "072", "subfields": {"@code":"aaa", "#text":"text"}} -> "072": {"aaa":"text"}
    # opakovane polia a podpolia da do zoznamu

    @staticmethod
    def move_tag_names(record):

        for controlfield in record.get('controlfield', []):
            tag = controlfield.get('@tag', None)
            if tag is not None:
                record[str(tag)] = controlfield.get('#text', None)
        record.pop('controlfield', None)

        for datafield in record.get('datafield', []):
            if isinstance(datafield.get('subfield', None), list):
                for subfield in datafield.get('subfield', []):
                    code = subfield.get('@code', None)
                    if code is not None:
                        existing_subfield = datafield.get(str(code), None)
                        new_subfield = subfield.get('#text', None)
                        if existing_subfield is not None:
                            if isinstance(existing_subfield, list):
                                existing_subfield.append(new_subfield)
                            else:
                                datafield[str(code)] = [existing_subfield, new_subfield]
                        else:
                            datafield[str(code)] = new_subfield
            else:
                subfield = datafield.get('subfield', None)
                code = subfield.get('@code', None)
                if code is not None:
                    datafield[str(code)] = subfield.get('#text', None)
            datafield.pop('subfield', None)
            tag = datafield.get('@tag', None)
            if tag is not None:
                existing_datafield = record.get(str(tag), None)
                if existing_datafield is not None:
                    if isinstance(existing_datafield, list):
                        existing_datafield.append(datafield)
                    else:
                        record[str(tag)] = [existing_datafield, datafield]
                else:
                    record[str(tag)] = datafield
            datafield.pop('@tag', None)
        record.pop('datafield', None)

    # importuje metadata do elastiku

    @staticmethod
    def import_metadata(path, index):

        es = Elasticsearch()

        number = 0
        error_log = []
        for event, elem in etree.iterparse(path, events=('end', 'start-ns')):
            if event == 'end':
                if '}' in elem.tag:
                    elem.tag = elem.tag.split('}', 1)[1]  # odstranenie namespace
                if elem.tag == "record":
                    number += 1
                    result = None
                    print("processing record number " + str(number))
                    try:
                        xmlstr = etree.tostring(elem, encoding='unicode', method='xml')
                        elem.clear()
                        result = xmltodict.parse(xmlstr)
                        result = result['record']  # odstranenie record tagu
                        DataImporter.move_tag_names(result)
                        if result.get('072', None) is None:
                            continue
                        if result.get('080', None) is None:
                            continue
                        if result.get('OAI', None) is None:
                            continue
                        if not DataImporter.is_in_language_dict(result, 'cze'):
                            continue
                    except Exception as error:
                        print("exception during proccesing record number: " + str(number))
                        error_log.append("exception during proccesing record number: " + str(number))
                        print(error)
                        error_log.append(error)
                        result = None
                        pass
                    if result is not None:
                        try:
                            es.index(index=index, doc_type="record", body=result)
                            es.indices.refresh(index=index)
                            print("saved record number " + str(number))
                        except exceptions.ElasticsearchException as elasticerror:
                            print("failed to save record number: " + str(number))
                            error_log.append("failed to save record number: " + str(number))
                            print(elasticerror)
                            error_log.append(str(elasticerror))
                            pass
        print(error_log)

    # importuje metada do elastiku
    # uklada az od zadaneho cisla

    @staticmethod
    def import_part_of_data(path, index, position_from):

        es = Elasticsearch()

        number = 0
        error_log = []
        for event, elem in etree.iterparse(path, events=('end', 'start-ns')):
            if event == 'end':
                if '}' in elem.tag:
                    elem.tag = elem.tag.split('}', 1)[1]  # odstranenie namespace
                if elem.tag == "record":
                    number += 1
                    if number < position_from:
                        elem.clear()
                        continue
                    result = None
                    print("processing record number " + str(number))
                    try:
                        xmlstr = etree.tostring(elem, encoding='unicode', method='xml')
                        elem.clear()
                        result = xmltodict.parse(xmlstr)
                        result = result['record']  # odstranenie record tagu
                        DataImporter.move_tag_names(result)
                        if result.get('072', None) is None:
                            continue
                        if result.get('080', None) is None:
                            continue
                        if result.get('OAI', None) is None:
                            continue
                    except Exception as error:
                        print("exception during proccesing record number: " + str(number))
                        error_log.append("exception during proccesing record number: " + str(number))
                        print(error)
                        error_log.append(error)
                        result = None
                        pass
                    if result is not None:
                        try:
                            es.index(index=index, doc_type="record", body=result)
                            es.indices.refresh(index=index)
                            print("saved record number " + str(number))
                        except exceptions.ElasticsearchException as elasticerror:
                            print("failed to save record number: " + str(number))
                            error_log.append("failed to save record number: " + str(number))
                            print(elasticerror)
                            error_log.append(elasticerror)
                            pass
        print(error_log)

    @staticmethod
    def get_all_keywords(path):

        number = 0
        error_log = []
        keywords = []
        for event, elem in etree.iterparse(path, events=('end', 'start-ns')):
            if event == 'end':
                if '}' in elem.tag:
                    elem.tag = elem.tag.split('}', 1)[1]  # odstranenie namespace
                if elem.tag == "record":
                    number += 1
                    result = None
                    print("processing record number " + str(number))
                    try:
                        xmlstr = etree.tostring(elem, encoding='unicode', method='xml')
                        elem.clear()
                        result = xmltodict.parse(xmlstr)
                        result = result['record']  # odstranenie record tagu
                        DataImporter.move_tag_names(result)
                        if result.get('650', None) is None:
                            continue
                        if not DataImporter.is_in_language_dict(result, 'cze'):
                            continue
                    except Exception as error:
                        print("exception during proccesing record number: " + str(number))
                        error_log.append("exception during proccesing record number: " + str(number))
                        print(error)
                        error_log.append(error)
                        result = None
                        pass
                    if result is not None:
                        field_650 = result.get('650', None)
                        if isinstance(field_650, (AttrDict, dict)):
                            field_650 = [field_650]
                        for field in field_650:
                            if field.get('2', '') == 'czenas':
                                try:
                                    if field['a'] not in keywords:
                                        keywords.append(field['a'])
                                except KeyError as ke:
                                    # print(ke)
                                    continue
                            else:
                                continue
        print(keywords)
        print(error_log)

    def import_fulltext(self, index, to_index):
        pairs = Helper.get_pairs('data/sloucena_id')
        te = TextExtractor('data/all', 'data/sorted_pages')
        te_pre = TextExtractorPre('data/all', 'data/sorted_pages')
        client = Elasticsearch()
        s = Search(using=client, index=index)
        s.execute()
        i = 0
        for hit in s.scan():
            hit = hit.to_dict()
            try:
                field_001 = hit['001']
                exists_query = Search(using=client, index=to_index).query(Q({"match": {"id_mzk": field_001}}))
                response = exists_query.execute()
                if len(response.hits) != 0:
                    continue
                field_072 = hit['072']
                if isinstance(field_072, (AttrDict, dict)):
                    field_072 = [field_072]
                field_080 = hit['080']
                if isinstance(field_080, (AttrDict, dict)):
                    field_080 = [field_080]
                field_650 = hit['650']
                if isinstance(field_650, (AttrDict, dict)):
                    field_650 = [field_650]
                oai = hit['OAI']['a']
                field_245 = hit['245']
            except KeyError as ke:
                # print(ke)
                continue
            field_020 = hit.get('020', "")
            if field_020 != "":
                if isinstance(field_020, list):
                    field_020 = field_020[0].get('a', '')
                else:
                    field_020 = field_020.get('a', '')
            konspekts = []
            for field in field_072:
                if field.get('2', "") == 'Konspekt':
                    try:
                        konspekts.append({'category': int(field['9']), 'group': field['a']})
                    except KeyError as ke:
                        # print(ke)
                        continue
                else:
                    continue
            if len(konspekts) == 0:
                continue
            keywords = []
            for field in field_650:
                if field.get('2', '') == 'czenas':
                    try:
                        if field['a'] not in keywords:
                            keywords.append(field['a'])
                    except KeyError as ke:
                        # print(ke)
                        continue
                else:
                    continue
            if len(keywords) == 0:
                continue
            mdts = []
            for field in field_080:
                try:
                    mdts.append(field['a'])
                except KeyError as ke:
                    # print(ke)
                    continue
            uuids = pairs.get(oai, None)
            if uuids is None:
                continue
            text = ""
            uuid = ""
            pre_text = ""
            # for ui in uuids:
            #     text = te.get_text(ui)
            #     if text != "":
            #         uuid = ui
            #         break
            # if text == "":
            #     continue
            for ui in uuids:
                pre_text = te_pre.get_text(ui)
                if pre_text != "":
                    uuid = ui
                    break
            if pre_text == "":
                continue
            pre_text_split = pre_text.split(' ')
            new_dict = {'id_mzk': field_001, 'uuid': uuid, 'oai': oai, 'isbn': field_020, 'text': "",
                        'czech': pre_text,
                        'text_pre': "", 'tags_pre': [], 'tags_elastic': [], 'keywords': keywords,
                        'konpsket': konspekts, 'mdt': mdts,
                        'title': field_245.get('a', "") + " " + field_245.get('b', ""),
                        'czech_length': len(pre_text_split)}
            print('saving number:' + str(i))
            try:
                client.index(index=to_index, body=new_dict, request_timeout=60)
            except exceptions.ElasticsearchException as elasticerror:
                print("couldnt save document uuid: " + uuid + " length of document: " + str(len(pre_text_split)))
                print(elasticerror)
                pass

            # client.indices.refresh(index=index_to)
            i += 1
            # break

    @staticmethod
    def is_in_language_dict(record, language):
        field_008 = record.get('008', None)
        field_041 = record.get('041', None)
        if field_008 is not None:
            if field_008.lower()[35:38] == language:
                return True
        if field_041 is not None:
            if isinstance(field_041, list):
                for field in field_041:
                    for subfield_a in field.get('a', []):
                        if subfield_a.lower() == language:
                            return True
            else:
                for subfield_a in field_041.get('a', []):
                    if subfield_a.lower() == language:
                        return True
        return False

    @staticmethod
    def count_czech_not_tagged(path):
        number_of_czech_not_taged = 0
        number_with_080 = 0
        number_with_multiple_080 = 0
        error_log = []
        for event, elem in etree.iterparse(path, events=('end', 'start-ns')):
            if event == 'end':
                if '}' in elem.tag:
                    elem.tag = elem.tag.split('}', 1)[1]  # odstranenie namespace
                if elem.tag == "record":
                    try:
                        xmlstr = etree.tostring(elem, encoding='unicode', method='xml')
                        elem.clear()
                        result = xmltodict.parse(xmlstr)
                        result = result['record']  # odstranenie record tagu
                        DataImporter.move_tag_names(result)
                        if result.get('072', None) is not None:
                            continue
                        if result.get('OAI', None) is None:
                            continue
                        field_080 = result.get('080', None)
                        if DataImporter.is_in_language_dict(result, "cze"):
                            number_of_czech_not_taged += 1
                        else:
                            continue
                        if field_080 is None:
                            continue
                        else:
                            number_with_080 += 1
                            if isinstance(field_080, list) or isinstance(field_080.get('a', None), list):
                                number_with_multiple_080 += 1
                    except Exception as error:
                        print(error)
                        error_log.append(str(error))
                        pass
        print("number of not tagged in czech: " + str(number_of_czech_not_taged))
        print("number of not tagged in czech with one 080: " + str(number_with_080))
        print("number of not tagged in czech with multiple 080: " + str(number_with_multiple_080))
        print(error_log)

    @staticmethod
    def count_tagged_keywords(path):
        have_note = 0
        have_entry = 0
        have_keyword = 0
        error_log = []
        for event, elem in etree.iterparse(path, events=('end', 'start-ns')):
            if event == 'end':
                if '}' in elem.tag:
                    elem.tag = elem.tag.split('}', 1)[1]  # odstranenie namespace
                if elem.tag == "record":
                    try:
                        xmlstr = etree.tostring(elem, encoding='unicode', method='xml')
                        elem.clear()
                        result = xmltodict.parse(xmlstr)
                        result = result['record']  # odstranenie record tagu
                        DataImporter.move_tag_names(result)
                        if result.get('072', None) is None:
                            continue
                        if result.get('OAI', None) is None:
                            continue
                        field_600 = result.get('600', None)
                        field_610 = result.get('610', None)
                        field_611 = result.get('611', None)
                        field_630 = result.get('630', None)
                        field_650 = result.get('650', None)
                        if field_600 is not None or field_610 is not None or field_611 is not None or \
                                field_630 is not None or field_650 is not None:
                            have_entry += 1
                            if field_650 is not None:
                                have_keyword += 1
                        for i in range(500, 600):
                            if result.get(str(i), None) is not None:
                                have_note += 1
                                break
                    except Exception as error:
                        print(error)
                        error_log.append(str(error))
                        pass
        print("number of having note: " + str(have_note))
        print("number of having entry: " + str(have_entry))
        print("number of having keyword: " + str(have_keyword))
        print(error_log)

    @staticmethod
    def get_tagged_missing_uuids(path):
        i = 0
        error_log = []
        pairs = Helper.get_pairs('data/sloucena_id')
        te = TextExtractor('data/all', 'data/sorted_pages')
        found_uuids = []
        for event, elem in etree.iterparse(path, events=('end', 'start-ns')):
            if event == 'end':
                if '}' in elem.tag:
                    elem.tag = elem.tag.split('}', 1)[1]  # odstranenie namespace
                if elem.tag == "record":
                    try:
                        xmlstr = etree.tostring(elem, encoding='unicode', method='xml')
                        elem.clear()
                        result = xmltodict.parse(xmlstr)
                        result = result['record']  # odstranenie record tagu
                        DataImporter.move_tag_names(result)
                        try:
                            field_001 = result['001']
                            field_072 = result['072']
                            oai = result['OAI']['a']
                            if not DataImporter.is_in_language_dict(result, 'cze'):
                                continue
                        except KeyError as ke:
                            continue
                        uuids = pairs.get(oai, None)
                        if uuids is None:
                            continue
                        for ui in uuids:
                            ui = ui + ".tar.gz"
                            if ui not in te.all_files:
                                found_uuids.append(ui)
                            else:
                                i += 1
                    except Exception as error:
                        print(error)
                        error_log.append(str(error))
                        pass
        print(i)
        print(len(found_uuids))
        with open('uuids5.txt', 'w+', encoding="utf-8") as f:
            for ui in found_uuids:
                f.write(ui)
                f.write('\n')

    @staticmethod
    def import_texts(texts_path, sorted_pages, index):
        for file in os.listdir(texts_path):
            if not file.endswith("tar.gz"):
                continue
            tar = tarfile.open(os.path.join(texts_path, file), "r:gz")
            tar.extractall(path=texts_path + "\\temp")
            tar.close()

    def get_missing_uuids(self, index):
        pairs = Helper.get_pairs('data/sloucena_id')
        te = TextExtractor('data/all', 'data/sorted_pages')
        client = Elasticsearch()
        s = Search(using=client, index=index)
        s.execute()
        found_uuids = []
        i = 0
        for hit in s.scan():
            hit = hit.to_dict()
            try:
                field_001 = hit['001']
                field_072 = hit['072']
                oai = hit['OAI']['a']
                # field_245 = hit['245']
                if not self.is_in_language_dict(hit, 'cze'):
                    continue
            except KeyError as ke:
                continue
            uuids = pairs.get(oai, None)
            if uuids is None:
                continue
            for ui in uuids:
                ui = ui + ".tar.gz"
                if ui not in te.all_files:
                    found_uuids.append(ui)
                else:
                    i += 1
        print(i)
        print(len(found_uuids))
        with open('uuids4.txt', 'w+', encoding="utf-8") as f:
            for ui in found_uuids:
                f.write(ui)
                f.write('\n')


index = 'records_mzk_filtered'
index_to = 'fulltext_mzk'
es = Elasticsearch()
# es.indices.delete(index=index_to)
mappings = {
    "mappings": {
        "_source": {
            "excludes": ["text", "czech"]
        },
        "properties": {
            "title": {
                "type": "keyword"
            },
            "text": {
                "type": "text",
                "analyzer": "fulltext_analyzer",
                "term_vector": "with_positions_offsets",
                "store": True,
                "index_options": "offsets"
            },
            "czech": {
                "type": "text",
                "analyzer": "fulltext_analyzer",
                "term_vector": "with_positions_offsets",
                "store": True,
                "index_options": "offsets"
            },
            "text_pre": {
                "type": "text",
                "term_vector": "with_positions_offsets",
                "store": True,
                "analyzer": "fulltext_analyzer",
                "index_options": "offsets"
            },
            "tags_pre": {
                "type": "text"
            },
            "tags_elastic": {
                "type": "text"
            },
            "keywords": {
                "type": "keyword"
            },
            "konspekt": {
                "type": "nested",
                "properties": {
                    "category": {
                        "type": "keyword"
                    },
                    "group": {
                        "type": "keyword"
                    }
                }
            },
            "mdt": {
                "type": "keyword"
            },
            "id_mzk": {
                "type": "keyword"
            },
            "uuid": {
                "type": "keyword"
            },
            "oai": {
                "type": "keyword"
            },
            "isbn": {
                "type": "keyword"
            },
            "czech_length": {
                "type": "long"
            }
        }
    },
    "settings": {
        "index.analyze.max_token_count": 20000,
        "index": {
            "number_of_shards": 1,
            "number_of_replicas": 0
        },
        "analysis": {
            "analyzer": {
                "czech": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": [
                        "czech_stop",
                        "czech_length",
                        "czech_hunspell",
                        "lowercase",
                        "czech_stop",
                        "unique_on_same_position"
                    ]
                },
                "fulltext_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": [
                        "lowercase"
                    ]
                }
            },
            "filter": {
                "czech_hunspell": {
                    "type": "hunspell",
                    "locale": "cs_CZ",
                    "dedup": True
                },
                "czech_stop": {
                    "type": "stop",
                    "stopwords": [
                        "že",
                        "_czech_"
                    ]
                },
                "czech_length": {
                    "type": "length",
                    "min": 2
                },
                "unique_on_same_position": {
                    "type": "unique",
                    "only_on_same_position": True
                }
            }
        }
    }
}
# response = es.indices.create(index=index_to, body=mappings)

# print(response)

# print(response)
path = 'C:\\Users\\jakub\\Documents\\metadata_nkp.xml'
di = DataImporter()
di.get_tagged_missing_uuids(path)
# di.get_missing_uuids(index)
# di.get_all_keywords(path)
# di.import_fulltext(index, index_to)
