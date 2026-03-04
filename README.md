# nir
мяу мяу
-----
по поводу бабагов:
щас там такая ошибка, предположительно по причине отсутствия обработки пустых символов:
```
Traceback (most recent call last):
  File "C:\Users\Mi\PycharmProjects\PythonProject\main.py", line 187, in <module>
    main()
  File "C:\Users\Mi\PycharmProjects\PythonProject\main.py", line 157, in main
    success2 = entity_assigner.process_document(doc, ontology_file)
  File "C:\Users\Mi\PycharmProjects\PythonProject\entity_assigner.py", line 167, in process_document
    if result_text.startswith("```json"):
AttributeError: 'NoneType' object has no attribute 'startswith'
```
-----
чтобы найти и получить потом свои резы, надо в конфиге поменять RESULTS_DIR и поставить ключ!! настя не воруй
-----
мяу мяу
