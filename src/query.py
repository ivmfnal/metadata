from expressions2 import Expression
import psycopg2, sys, getopt
import random

def sample(inputs, params):
    inp = inputs[0]
    fraction = params[0]
    x = 0.0
    for f in inp:
        x += fraction
        if x >= 1.0:
            x -= 1.0
            yield f
            
filters = dict(sample = sample)

connstr = sys.argv[1]

conn = psycopg2.connect(connstr)

queries = [
        ("minus",    
        """
                dataset Dataset1 - dataset Dataset2
        """), 

        ("union",    """
                [
                    dataset test:Dataset1, 
                    dataset test:Dataset2
                ]
        """),
        
        ("meta_filter, interaection", """
            {   
                dataset test:Dataset1, 
                dataset test:Dataset2
            } 
            where i > 10
        """),
    
        ("sample",   
        """
                filter sample(0.5) (dataset test:Dataset3 where b == true)
        """
        ),
    
    
        ("meta int", """
                dataset test:Dataset3 where i=5
        """)
]

for qn, qtext in queries:
    exp = Expression(conn, qtext, default_namespace = "test")
    out = list(exp.evaluate(filters))
    print (qn,":   ",sorted([f.Name for f in out]))


        
