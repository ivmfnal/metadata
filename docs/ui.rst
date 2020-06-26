Command Line Interface
======================

Installation
------------

You will need Python 3.7 or newer.

To install the client side components:

      .. code-block:: shell

          git clone https://github.com/ivmfnal/metadata.git
          mkdir ~/build
          cd metadata
          make # this will create ~/build/metadata and 
               # a tar file with contents of ~/build/metadata
          pip install --user requests 


You can use the client components from ~/metadata/build or from some other location where you untar the tar file created by make

Environment
-----------

To set the client environment:

  1. Create config YAML file:
  
      .. code-block:: yaml
      
          Server:
              URL:    http://host.fnal.gov:8080

  2. Set PYTHONPATH:
  
      .. code-block:: shell
      
          export PYTHONPATH=~/build/metadata/lib:~/build/metadata/ui:$PYTHONPATH
          export PATH=~/build/metadata/ui:$PATH
          export METACAT_CONFIG=/path/to/config.yaml

Authentication
--------------

    .. code-block:: shell
    
        metacat auth login <username>           # login, will create/update ~/.metacat_tokens
        metacat auth whomi                      # shows current token username and expiration
        
Namespaces
----------

Currently done via GUI only


Datasets
--------

    .. code-block:: shell
    
        metacat dataset list [[<namespace pattern>:]<name pattern>]     - list datasets
        # examples:
        # metacat dataset list ns1:*
        # metacat dataset list *:A*
        
        metacat dataset create [-p <parent namespace>:<parent name>] <namespace>:<name>
        metacat dataset show <namespace>:<name>
        
        
File Metadata
-------------

Declaration
~~~~~~~~~~~

    Create JSON file with metadata:

    .. code-block:: 
    
        [
            {   
                "namespace":"...",          # optional  - command line default witll be used
                "name":"...",               # required
                "fid":"...",                # optional
                "metadata": { ... },        # optional
                "parents":  [ "fid1", "fid2", ... ]     # optional         
            },
            ...
        ]

    .. code-block:: shell
    
        # declare new files:
        metacat file declare [-n <default namespace>] metadata.json [<namespace>:]<dataset>
        
        
Updating
~~~~~~~~

    Create JSON file with (new) metadata:

    .. code-block:: 
    
        [
            {   
                "namespace":"...",          # optional  - command line default witll be used
                "name":"...",               # optional
                "fid":"...",                # optional - either fid or namespace/name must be present
                "metadata": { ... },        # optional
                "parents":  [ "fid1", "fid2", ... ]     # optional         
            },
            ...
        ]

    .. code-block:: shell
    
        # declare new files:
        metacat file update [-n <default namespace>] metadata.json
        

        
Retrieving
~~~~~~~~~~

    .. code-block:: shell

        metacat file show <namespace>:<name>            # - by namespace/name
        metacat file show -i <fid>                      # - by file id
        
        
Adding files to dataset
~~~~~~~~~~~~~~~~~~~~~~~

    .. code-block:: shell
    
        metacat add <namespace>:<name> <dataset namespace>:<dataset name>
        metacat add -i <file id> <dataset namespace>:<dataset name>
        
Or using a JSON file with multiple files, create the JSON file:

    .. code-block:: 
    
        [
            {   
                "namespace":"...",          # optional  - command line default witll be used
                "name":"...",               # optional
                "fid":"...",                # optional - either fid or namespace/name must be present
            },
            ...
        ]
        
    .. code-block:: shell
    
        metacat add -f <json file> [-n <default namespace>] [<dataset namespace>:]<dataset name>

