from expressions import Expression
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

connstr = sys.argv[1]

conn = psycopg2.connect(connstr)

exp = Expression(conn, 
    [   "minus",
        [   "from", "test:Dataset1" ],
        [   "from", "test:Dataset2"  ]
    ]
)
    
exp2 = Expression(conn, 
    [ "filter", "sample", [0.75], 
	    [   "from", "test:Dataset1"	]
    ],
    {"sample":sample}
)
    
exp2 = Expression(conn, 
    [   "from", "test:Dataset2"  ]
)


queries = {
	"minus":	Expression(conn,
	    [   "minus",
		[   "from", "test:Dataset1" ],
		[   "from", "test:Dataset2"  ]
	    ]
	),
	"union":	Expression(conn, 
	    [   "or",
		[   "from", "test:Dataset1" ],
		[   "from", "test:Dataset2"  ]
	    ]
	),
	"sample":	Expression(conn, 
	    [ "filter", "sample", [0.5], 
		    [   "from", "test:Dataset3"	]
	    ],
	    {"sample":sample}
	),
        "meta int":	Expression(conn,
		[ "from", "test:Dataset3", ["i", "=", 5] ]
	),
        "meta bool":	Expression(conn,
		[ "from", "test:Dataset3", ["b", "=", True] ]
	)
}

for qn, q in sorted(queries.items()):
	out = list(q())
	print (qn,":   ",sorted([f.Name for f in out]))


        
