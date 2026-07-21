# JSON-Id-Value-Finder
This JSON Parsor code can easily able to find the values of any id of type: Id, String_Id, Boolean_Id.
Note: Python file and JSON file must lie in same location.

Example 1: 
-  terminal command :> python JSONParser.py "json_data_file.json" --field-id "field:forum_topic_id"
Output: 
-  Field ID: field:forum_topic_id
-  Total Occurrences : 107075
-  Null Values       : 107075
-  Non-Null Values   : 0


Example 1: 
-  terminal command :> python JSONParser.py "json_data_file.json" --field-id 360043048031
Output:                 
-  Field ID: 23071672052877
-  Total Occurrences : 214150
-  Null Values       : 213764
-  Non-Null Values   : 386
    Value Distribution:
    --------------------
-   "Self" : 154
-   "Office" : 116
-   "kiosk" : 56
-   "shop" : 30
-   "Inventory" : 16
-   "Home" : 12
-   "Cart" : 2"
