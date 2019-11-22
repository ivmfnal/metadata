from expressions4 import Query
import psycopg2, sys, getopt, time
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
            with namespace="test"
                (dataset A - dataset B)
        """), 
        ("mult",    """
		with namespace="test"
		(
                    dataset test:A			# comment
                    * dataset test:B
		)
        """),
        
        ("meta_filter, interaection", """
            {   
                dataset test:A, 
                dataset test:B
            } 
            where i > 10
        """),
    
        ("sample",   
        """
                filter sample(0.1) (dataset test:K where b == true)
        """
        ),
    
        ("meta int", """
                dataset test:C where i < 10
        """)
]

_queries = [
        ("sample",   
        """
                filter sample(0.5) (dataset test:C)
        """
        )
]
    


for qn, qtext in queries:
    exp = Query(conn, qtext, default_namespace = "t")
    t0 = time.time()
    out = list(exp.run(filters))
    dt = time.time() - t0
    print (qn,f"{dt:.3}","\n    -> ",sorted([f.Name for f in out]))


        
