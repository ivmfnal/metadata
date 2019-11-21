MQL - Metadata Query Language
=============================

Introduction
------------
One of the functions of the Metadata Database is to produce list of files matching a set of crieria specidied
by the user. The product has its own simple language to write these queries in called MQL (pronpounced: MEE-quel,
like sequel, but with M).

Dataset Query
-------------

The simplest MQL query you can write is a *Dataset Query*, which looks like this:

.. code-block:: sql

        dataset MyScope:MyDataset
        
This query simply returns all the files included in the dataset "MyScope:MyDataset".

Metadata Filtering
------------------

Results of any query can be filtered by adding some metadata criteria expression, called *meta-filter*:

.. code-block:: sql

        dataset MyScope:MyDataset
                where x > 0.5
                
This will return all the files in the dataset, which have a floating point metadata field named "x" with value greater than 0.5. A meta-filter can be more complicated:

.. code-block:: sql

        dataset MyScope:MyDataset
                where x > 0.5 and x < 1.5 
                        and run = 123 
                        and ( type="MC" or type="Data" )
                        
Generally, all white space is ignored in MQL.
                
Combining Queries
-----------------

Queries can be combined using boolean operations *union*, *join*, and subtraction to produce new queries:

.. code-block:: sql

        union(
                dataset MC:Cosmics
                        where p > 0.5 and p < 1.5 
                dataset MC:Beam where e = 10
        )
        
This query will return files from both datasets. Even if the individual queries happen to produce overallping
sets of files, each file will appear only *once* in the results of the *union* query.

Queries can be *joined* to procude the intersection of the results of individual queries:

.. code-block:: sql

        join(
                dataset MC:All
                        where p > 0.5 and p < 1.5 
                dataset MC:All
                        where e = 10
        )
        
Of course this is equivalent to:

.. code-block:: sql

        dataset MC:All
                where p > 0.5 and p < 1.5 and e = 10
        
Queries can be subtracted from each other, which means the resulting set will be boolean subtraction of second query
result set from the first:

.. code-block:: sql

        dataset MC:Beam where e1 > 10 - dataset MC:Exotics
        
Although is it not necessary in this example, you can use parethesis and white space to make the query more readable:

.. code-block:: sql

        (dataset MC:Beam where e1 > 10) 
        - (dataset MC:Exotics where type = "abcd")

Also, you can use square and curly brackets as an alternative to using explicit words "union" and "join" respectively.
The following two queries are equivalent:

.. code-block:: sql

        [
                dataset s:A,
                {
                        dataset s:B,
                        dataset s:C
                }
        ]

        union (
                dataset s:A,
                join(
                        dataset s:B,
                        dataset s:C
                )
        )
        
External Filters
----------------

The Meatadata Database Query Engine lets the user add custom Python code to be used as a more complicated
operations on the file sets. They in the Query Language, they are invoked using "filter" keyword:

.. code-block:: sql

        filter sample(0.5)( dataset s:A )
        
Here, *filter* the the keyword, *sample* is the name of the Python function to be used to filter the results
of the argument query (simple "dataset s:A" query in this case). As you can see, you can pass some
parameters to the function (the number 0.5).

A filter can accept multiple parameters and/or queries:

.. code-block:: sql

        filter process(0.5, 1, 3.1415)
                ( dataset s:A, dataset s:B - dataset s:D )

The user supplied function looks like ths:

.. code-block:: Python

        def process(params, inputs):
                # ...
                return iterable
                
The *params* argument will receive the pist of parameters and the *inputs* will get the list of
input file sets. The function is supposed to return a single iterable (a list, a generator, etc.) as the
output file set.


Common Namesaces
----------------

Typically (but not necessarily), all the datasets mentioned in a query refer to the same namespace.
You can avoid repeting the same namespace using "with" clause. The following are equivalent:

.. code-block:: sql

        with namespace="s"
        {
                dataset B,
                dataset C
        }

        {
                dataset s:B,
                dataset s:C
        }

Each "with" clause has its scope limited to the immediate query it is attached to. For example:

.. code-block:: sql

        with namespace="s"      
                dataset A - dataset B
        
because the namespace "s" is applied to dataset A, but not to "dataset B". The following would work though:

.. code-block:: sql

        with namespace="s"      
                (dataset A - dataset B)
        
And the outer "with" clause can be overridden by the inner clause:

.. code-block:: sql

        with namespace = "x"
                union (
                        dataset A,
                        with namespace = "y"
                                join(
                                        dataset B,
                                        dataset C
                                ),
                        dataset D
                )
                
In this example, datasets A and D will be assumed to be in the namespace "x", and datasets B and C - in
namespace "y".






        
