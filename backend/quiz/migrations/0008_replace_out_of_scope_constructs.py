from django.db import migrations
from django.utils import timezone


# Frozen question data keeps this migration deterministic after future bank edits.
REPLACEMENTS = [{'old': {'text': 'What is the type of the result?',
          'code_snippet': 'x = 3 + 2j\nprint(type(x))',
          'difficulty': 'medium',
          'choices': [{'text': "<class 'float'>",
                       'is_correct': False,
                       'explanation': 'Wrong. The `j` suffix marks an imaginary part, making the '
                                      'literal a complex number, not a float.'},
                      {'text': "<class 'int'>",
                       'is_correct': False,
                       'explanation': 'Wrong. Adding an integer and an imaginary number produces a '
                                      'complex number. There is no way to get `int` here.'},
                      {'text': "<class 'complex'>",
                       'is_correct': True,
                       'explanation': 'Correct. `2j` is an imaginary-part literal; Python promotes '
                                      "`3 + 2j` to `complex`. `complex` is one of Python's three "
                                      'numeric types along with `int` and `float`.'},
                      {'text': 'SyntaxError',
                       'is_correct': False,
                       'explanation': 'Wrong. `j` (or `J`) is valid Python syntax for the '
                                      'imaginary unit in complex numeric literals.'}],
          'module': 'module1'},
  'new': {'text': 'What does this print?',
          'code_snippet': 'distance = 3e2\nprint(type(distance), distance)',
          'difficulty': 'medium',
          'choices': [{'text': "<class 'int'> 300",
                       'is_correct': False,
                       'explanation': 'Wrong. Scientific notation creates a floating-point value '
                                      'here, even though its numeric value is a whole number.'},
                      {'text': "<class 'float'> 3.0",
                       'is_correct': False,
                       'explanation': 'Wrong. `3e2` means 3 multiplied by 10 squared, so its value '
                                      'is 300.0.'},
                      {'text': "<class 'float'> 300.0",
                       'is_correct': True,
                       'explanation': 'Correct. `3e2` is scientific notation for 3 × 10². Python '
                                      'represents this literal as the float `300.0`.'},
                      {'text': 'SyntaxError',
                       'is_correct': False,
                       'explanation': 'Wrong. An `e` followed by an exponent is valid scientific '
                                      'notation in a numeric literal.'}],
          'module': 'module1'}},
 {'old': {'text': 'What does this print?',
          'code_snippet': 'x = 5\nprint(type(x).__name__)',
          'difficulty': 'medium',
          'choices': [{'text': 'int',
                       'is_correct': True,
                       'explanation': 'Correct. `type(x)` returns the class object `<class '
                                      "'int'>`. Every class exposes its name through the "
                                      '`__name__` attribute, so the printed value is the plain '
                                      'string `int`.'},
                      {'text': "<class 'int'>",
                       'is_correct': False,
                       'explanation': 'Wrong. That is the repr of `type(x)` itself. By accessing '
                                      "`.__name__` you get only the string `'int'`."},
                      {'text': 'integer',
                       'is_correct': False,
                       'explanation': "Wrong. Python's built-in class is literally called `int`, "
                                      'not `integer`.'},
                      {'text': 'AttributeError',
                       'is_correct': False,
                       'explanation': 'Wrong. Every class (including `int`) has a `__name__` '
                                      'attribute.'}],
          'module': 'module1'},
  'new': {'text': 'What does this print?',
          'code_snippet': 'value = 0b1010 + 0o2\nprint(value)',
          'difficulty': 'medium',
          'choices': [{'text': '12',
                       'is_correct': True,
                       'explanation': 'Correct. Binary `0b1010` is decimal 10 and octal `0o2` is '
                                      'decimal 2, so their sum is 12.'},
                      {'text': '10',
                       'is_correct': False,
                       'explanation': 'Wrong. This ignores the octal operand `0o2`, whose decimal '
                                      'value is 2.'},
                      {'text': '0b1100',
                       'is_correct': False,
                       'explanation': 'Wrong. `print` displays the integer in decimal by default, '
                                      'so the sum is shown as `12`, not as a binary literal.'},
                      {'text': 'SyntaxError',
                       'is_correct': False,
                       'explanation': 'Wrong. The `0b` and `0o` prefixes are valid binary and '
                                      'octal integer notation.'}],
          'module': 'module1'}},
 {'old': {'text': 'What is the output?',
          'code_snippet': 'print(type(10 / 2).__name__)',
          'difficulty': 'medium',
          'choices': [{'text': 'float',
                       'is_correct': True,
                       'explanation': 'Correct. In Python 3 `/` is true division and always '
                                      'returns a float, even when the result is whole (5.0).'},
                      {'text': 'int',
                       'is_correct': False,
                       'explanation': 'Wrong. `/` never returns int in Python 3; use `//` for an '
                                      'int result.'},
                      {'text': 'number',
                       'is_correct': False,
                       'explanation': 'Wrong. There is no `number` type; the class name is '
                                      '`float`.'},
                      {'text': 'double',
                       'is_correct': False,
                       'explanation': 'Wrong. Python has no `double` type; floating-point values '
                                      'are `float`.'}],
          'module': 'module1'},
  'new': {'text': 'What does this print?',
          'code_snippet': 'value = 10 / 2\nprint(value == 5, value)',
          'difficulty': 'medium',
          'choices': [{'text': 'True 5.0',
                       'is_correct': True,
                       'explanation': 'Correct. True division produces the float `5.0`, and '
                                      'numeric equality considers `5.0` equal to the integer `5`.'},
                      {'text': 'False 5.0',
                       'is_correct': False,
                       'explanation': 'Wrong. Integers and floats with the same numeric value '
                                      'compare equal, so `5.0 == 5` is True.'},
                      {'text': 'True 5',
                       'is_correct': False,
                       'explanation': 'Wrong. The comparison is True, but `/` performs true '
                                      'division and the value printed is the float `5.0`.'},
                      {'text': 'False 5',
                       'is_correct': False,
                       'explanation': 'Wrong. `/` produces `5.0`, and that float compares equal to '
                                      'the integer 5.'}],
          'module': 'module1'}},
 {'old': {'text': 'What does this print?',
          'code_snippet': 'a, *b, c = [10, 20, 30, 40, 50]\nprint(b)',
          'difficulty': 'hard',
          'choices': [{'text': '[20, 30, 40]',
                       'is_correct': True,
                       'explanation': 'Correct. In extended unpacking, the starred target `*b` '
                                      'collects all remaining elements between the other targets '
                                      'into a LIST. `a` takes 10, `c` takes 50, and `b` gets the '
                                      'middle `[20, 30, 40]`.'},
                      {'text': '(20, 30, 40)',
                       'is_correct': False,
                       'explanation': 'Wrong. `*target` in an assignment always produces a LIST, '
                                      "regardless of the iterable's type on the right."},
                      {'text': '20',
                       'is_correct': False,
                       'explanation': 'Wrong. The starred name absorbs ALL remaining elements '
                                      'between the fixed targets, not just one.'},
                      {'text': 'ValueError',
                       'is_correct': False,
                       'explanation': 'Wrong. With exactly one starred target, any iterable with '
                                      'enough elements for the non-starred names unpacks '
                                      'cleanly.'}],
          'module': 'module3'},
  'new': {'text': 'What does this print?',
          'code_snippet': 'numbers = [10, 20, 30]\n'
                          'copy = numbers[:]\n'
                          'copy[1] = 99\n'
                          'print(numbers[1], copy[1])',
          'difficulty': 'hard',
          'choices': [{'text': '20 99',
                       'is_correct': True,
                       'explanation': 'Correct. A full slice creates a new list. Changing index 1 '
                                      'in `copy` therefore leaves `numbers[1]` equal to 20.'},
                      {'text': '99 99',
                       'is_correct': False,
                       'explanation': 'Wrong. This would happen if `copy = numbers` created an '
                                      'alias; `numbers[:]` creates a separate list.'},
                      {'text': '20 20',
                       'is_correct': False,
                       'explanation': 'Wrong. The assignment changes `copy[1]` to 99 even though '
                                      'the original list stays unchanged.'},
                      {'text': 'IndexError',
                       'is_correct': False,
                       'explanation': 'Wrong. Index 1 exists in both three-element lists.'}],
          'module': 'module3'}},
 {'old': {'text': 'What does this print?',
          'code_snippet': 'squares = {n: n * n for n in range(1, 4)}\nprint(squares)',
          'difficulty': 'medium',
          'choices': [{'text': '{1: 1, 2: 4, 3: 9}',
                       'is_correct': True,
                       'explanation': 'Correct. This is a DICT comprehension: `{key_expr: '
                                      'value_expr for var in iterable}`. For n in 1,2,3 you get '
                                      '1→1, 2→4, 3→9.'},
                      {'text': '{1, 4, 9}',
                       'is_correct': False,
                       'explanation': 'Wrong. Curly braces with `expr for …` (no colon) make a SET '
                                      'comprehension. With `key: value` you get a dict.'},
                      {'text': '[1, 4, 9]',
                       'is_correct': False,
                       'explanation': 'Wrong. Square brackets would be a list comprehension; curly '
                                      'braces with `key: value` produce a dict.'},
                      {'text': 'SyntaxError',
                       'is_correct': False,
                       'explanation': 'Wrong. Dict comprehensions are a core Python feature (since '
                                      '2.7/3.0).'}],
          'module': 'module3'},
  'new': {'text': 'What does this print?',
          'code_snippet': "scores = {'Ann': 2, 'Bob': 3}\n"
                          "scores['Ann'] += scores['Bob']\n"
                          "print(scores['Ann'])",
          'difficulty': 'medium',
          'choices': [{'text': '5',
                       'is_correct': True,
                       'explanation': 'Correct. The value under `Ann` starts at 2 and is increased '
                                      'by the value 3 stored under `Bob`.'},
                      {'text': '2',
                       'is_correct': False,
                       'explanation': 'Wrong. The augmented assignment updates the value stored '
                                      'under the `Ann` key.'},
                      {'text': '3',
                       'is_correct': False,
                       'explanation': 'Wrong. That is the value read from `Bob`; it is added to '
                                      'the existing value 2 under `Ann`.'},
                      {'text': 'KeyError',
                       'is_correct': False,
                       'explanation': 'Wrong. Both `Ann` and `Bob` already exist as dictionary '
                                      'keys.'}],
          'module': 'module3'}},
 {'old': {'text': 'What does this print?',
          'code_snippet': "name, qty = 'apple', 7\nprint(f'{qty} {name}s cost {qty * 0.5:.2f}')",
          'difficulty': 'medium',
          'choices': [{'text': '7 apples cost 3.50',
                       'is_correct': True,
                       'explanation': 'Correct. f-strings embed expressions in `{…}`. `{qty}` → 7, '
                                      '`{name}s` → `apples`, `{qty * 0.5:.2f}` formats the number '
                                      'with 2 decimals → `3.50`.'},
                      {'text': '7 apples cost 3.5',
                       'is_correct': False,
                       'explanation': 'Wrong. The `:.2f` format spec forces EXACTLY two digits '
                                      'after the decimal point — so `3.5` becomes `3.50`.'},
                      {'text': 'qty apples cost 3.50',
                       'is_correct': False,
                       'explanation': 'Wrong. Inside an f-string, names in `{…}` are substituted '
                                      'with their values, not left as literal text.'},
                      {'text': 'SyntaxError',
                       'is_correct': False,
                       'explanation': 'Wrong. f-strings and format specifiers (`:.2f`) are '
                                      'standard Python 3.6+ syntax.'}],
          'module': 'module3'},
  'new': {'text': 'What does this print?',
          'code_snippet': "quantity = 7\nitem = 'apple'\nprint(str(quantity) + ' ' + item + 's')",
          'difficulty': 'medium',
          'choices': [{'text': '7 apples',
                       'is_correct': True,
                       'explanation': "Correct. `str(quantity)` produces `'7'`, and string "
                                      'concatenation joins it with a space, `apple`, and `s`.'},
                      {'text': '7 apple',
                       'is_correct': False,
                       'explanation': "Wrong. The final `+ 's'` appends an `s` to the item name."},
                      {'text': 'quantity apples',
                       'is_correct': False,
                       'explanation': 'Wrong. `str(quantity)` converts the value of the variable, '
                                      '7; it does not use the variable name as text.'},
                      {'text': 'TypeError',
                       'is_correct': False,
                       'explanation': 'Wrong. The integer is converted with `str` before all '
                                      'operands are concatenated as strings.'}],
          'module': 'module3'}},
 {'old': {'text': 'What is the output?',
          'code_snippet': "print(list(enumerate('ab'))[1])",
          'difficulty': 'hard',
          'choices': [{'text': "(1, 'b')",
                       'is_correct': True,
                       'explanation': "Correct. `enumerate('ab')` yields (0, 'a'), (1, 'b'); index "
                                      "1 is the (1, 'b') pair."},
                      {'text': "'b'",
                       'is_correct': False,
                       'explanation': 'Wrong. `enumerate` produces (index, value) pairs, so '
                                      'element 1 is a tuple.'},
                      {'text': "(1, 'a')",
                       'is_correct': False,
                       'explanation': "Wrong. At position 1 the character is 'b', not 'a'."},
                      {'text': '1',
                       'is_correct': False,
                       'explanation': "Wrong. The element is the whole (1, 'b') tuple, not just "
                                      'the index.'}],
          'module': 'module3'},
  'new': {'text': 'What does this print?',
          'code_snippet': "record = ([1, 2], 'ok')\nrecord[0][1] = 9\nprint(record)",
          'difficulty': 'hard',
          'choices': [{'text': "([1, 9], 'ok')",
                       'is_correct': True,
                       'explanation': 'Correct. The tuple itself is unchanged, but its first '
                                      'element is a mutable list whose item can be replaced.'},
                      {'text': "([1, 2], 'ok')",
                       'is_correct': False,
                       'explanation': 'Wrong. Tuple immutability does not prevent mutation inside '
                                      'the list stored as one of its elements.'},
                      {'text': "([9, 2], 'ok')",
                       'is_correct': False,
                       'explanation': 'Wrong. Index 1 selects the second list element, so 2 '
                                      'becomes 9; index 0 remains 1.'},
                      {'text': 'TypeError',
                       'is_correct': False,
                       'explanation': 'Wrong. The code assigns to an item of the nested list, not '
                                      'to an item of the tuple.'}],
          'module': 'module3'}},
 {'old': {'text': 'What does this print?',
          'code_snippet': 'sq = lambda x: x * x\nprint(sq(4))',
          'difficulty': 'easy',
          'choices': [{'text': '16',
                       'is_correct': True,
                       'explanation': 'Correct. `lambda x: x * x` is an anonymous function taking '
                                      '`x` and returning `x*x`. Called with 4, it returns 16.'},
                      {'text': '4',
                       'is_correct': False,
                       'explanation': 'Wrong. The lambda body is `x * x`, not `x`.'},
                      {'text': 'SyntaxError',
                       'is_correct': False,
                       'explanation': 'Wrong. `lambda` is valid Python syntax for anonymous '
                                      'single-expression functions.'},
                      {'text': 'TypeError',
                       'is_correct': False,
                       'explanation': 'Wrong. `int * int` is valid multiplication.'}],
          'module': 'module4'},
  'new': {'text': 'What does this print?',
          'code_snippet': 'def difference(left, right):\n'
                          '    return left - right\n'
                          '\n'
                          'print(difference(9, 4))',
          'difficulty': 'easy',
          'choices': [{'text': '5',
                       'is_correct': True,
                       'explanation': 'Correct. The function returns `left - right`, so '
                                      '`difference(9, 4)` returns 5.'},
                      {'text': '13',
                       'is_correct': False,
                       'explanation': 'Wrong. The function subtracts its second argument; it does '
                                      'not add the two values.'},
                      {'text': '-5',
                       'is_correct': False,
                       'explanation': 'Wrong. Positional arguments bind `left` to 9 and `right` to '
                                      '4, so the order is `9 - 4`.'},
                      {'text': 'None',
                       'is_correct': False,
                       'explanation': 'Wrong. The explicit `return` statement supplies the value '
                                      '5.'}],
          'module': 'module4'}},
 {'old': {'text': 'What does this print?',
          'code_snippet': 'def outer():\n'
                          '    x = 1\n'
                          '    def inner():\n'
                          '        nonlocal x\n'
                          '        x += 10\n'
                          '    inner()\n'
                          '    return x\n'
                          '\n'
                          'print(outer())',
          'difficulty': 'hard',
          'choices': [{'text': '1',
                       'is_correct': False,
                       'explanation': 'Wrong. `nonlocal x` binds the inner `x` to the enclosing '
                                      "`outer` scope. The `x += 10` thus mutates `outer`'s `x`."},
                      {'text': '11',
                       'is_correct': True,
                       'explanation': 'Correct. `nonlocal x` tells `inner` that `x` refers to the '
                                      'nearest enclosing (non-global) scope, which is `outer`. `x '
                                      '+= 10` updates that `x` from 1 to 11. `outer` then returns '
                                      '11.'},
                      {'text': 'UnboundLocalError',
                       'is_correct': False,
                       'explanation': 'Wrong. `nonlocal` resolves the scoping issue that would '
                                      'otherwise cause this error.'},
                      {'text': 'SyntaxError',
                       'is_correct': False,
                       'explanation': 'Wrong. `nonlocal` is a keyword (Python 3) specifically for '
                                      'this purpose.'}],
          'module': 'module4'},
  'new': {'text': 'What does this print?',
          'code_snippet': 'value = 1\n'
                          '\n'
                          'def outer():\n'
                          '    value = 10\n'
                          '    def inner():\n'
                          '        value = 100\n'
                          '        return value\n'
                          '    return inner() + value\n'
                          '\n'
                          'print(outer(), value)',
          'difficulty': 'hard',
          'choices': [{'text': '100 1',
                       'is_correct': False,
                       'explanation': 'Wrong. `outer` adds the 100 returned by `inner` to its own '
                                      'local value 10 before returning.'},
                      {'text': '110 1',
                       'is_correct': True,
                       'explanation': 'Correct. Each assignment creates a value in its own scope: '
                                      '`inner` returns 100, `outer` adds its local 10, and the '
                                      'global remains 1.'},
                      {'text': '110 10',
                       'is_correct': False,
                       'explanation': 'Wrong. The `value = 10` assignment is local to `outer` and '
                                      'does not change the global variable.'},
                      {'text': 'UnboundLocalError',
                       'is_correct': False,
                       'explanation': 'Wrong. Each function reads a local variable after assigning '
                                      'it, so no unbound local access occurs.'}],
          'module': 'module4'}},
 {'old': {'text': 'What does this print?',
          'code_snippet': 'add = lambda x, y=10: x + y\nprint(add(3), add(3, 4))',
          'difficulty': 'medium',
          'choices': [{'text': '13 7',
                       'is_correct': True,
                       'explanation': 'Correct. Lambdas support default parameter values just like '
                                      '`def`. `add(3)` uses `y=10` → 13; `add(3, 4)` overrides it '
                                      '→ 7.'},
                      {'text': '13 34',
                       'is_correct': False,
                       'explanation': 'Wrong. `+` on integers is numeric addition, not '
                                      'concatenation.'},
                      {'text': 'SyntaxError',
                       'is_correct': False,
                       'explanation': 'Wrong. `lambda x, y=10: …` — default parameters are allowed '
                                      'in lambdas.'},
                      {'text': 'TypeError: missing argument',
                       'is_correct': False,
                       'explanation': 'Wrong. `y` has a default, so calling `add(3)` with only one '
                                      'argument is fine.'}],
          'module': 'module4'},
  'new': {'text': 'What does this print?',
          'code_snippet': 'def add(x, y=10):\n    return x + y\n\nprint(add(3), add(3, 4))',
          'difficulty': 'medium',
          'choices': [{'text': '13 7',
                       'is_correct': True,
                       'explanation': 'Correct. The first call uses the default `y=10`; the second '
                                      'call supplies 4 instead, producing 13 and 7.'},
                      {'text': '13 34',
                       'is_correct': False,
                       'explanation': 'Wrong. The second call adds two integers; it does not '
                                      'concatenate their digits.'},
                      {'text': '7 7',
                       'is_correct': False,
                       'explanation': 'Wrong. Only the second call overrides `y`; the first call '
                                      'uses its default value 10.'},
                      {'text': 'TypeError: missing argument',
                       'is_correct': False,
                       'explanation': 'Wrong. The parameter `y` has a default, so `add(3)` is a '
                                      'valid call.'}],
          'module': 'module4'}},
 {'old': {'text': 'What does this print?',
          'code_snippet': 'try:\n'
                          "    raise KeyError('k')\n"
                          'except (ValueError, KeyError) as e:\n'
                          "    print('caught', type(e).__name__)",
          'difficulty': 'medium',
          'choices': [{'text': 'caught KeyError',
                       'is_correct': True,
                       'explanation': 'Correct. A tuple of exception types in `except` catches any '
                                      'of them. `as e` binds the caught exception to the name `e`; '
                                      "`type(e).__name__` is the exception's class name, "
                                      '`KeyError`.'},
                      {'text': 'caught ValueError',
                       'is_correct': False,
                       'explanation': 'Wrong. The exception actually raised is `KeyError`. The '
                                      "tuple only tells `except` which types to catch; it doesn't "
                                      'rename the exception.'},
                      {'text': 'caught Exception',
                       'is_correct': False,
                       'explanation': 'Wrong. `type(e).__name__` gives the SPECIFIC class name of '
                                      'the raised exception, not its base class.'},
                      {'text': 'KeyError propagates (uncaught)',
                       'is_correct': False,
                       'explanation': "Wrong. `KeyError` IS listed in the exception tuple, so it's "
                                      'caught.'}],
          'module': 'module4'},
  'new': {'text': 'What does this print?',
          'code_snippet': 'try:\n'
                          "    raise KeyError('missing')\n"
                          'except (ValueError, KeyError):\n'
                          "    print('caught')",
          'difficulty': 'medium',
          'choices': [{'text': 'caught',
                       'is_correct': True,
                       'explanation': 'Correct. An exception tuple catches any listed type, and '
                                      '`KeyError` is one of the two types in this handler.'},
                      {'text': 'missing',
                       'is_correct': False,
                       'explanation': 'Wrong. The handler prints the fixed string `caught`; it '
                                      'does not print the exception message.'},
                      {'text': 'ValueError',
                       'is_correct': False,
                       'explanation': 'Wrong. The tuple lists catchable types but does not convert '
                                      'the raised `KeyError` into `ValueError`.'},
                      {'text': 'KeyError propagates',
                       'is_correct': False,
                       'explanation': 'Wrong. `KeyError` appears explicitly in the exception '
                                      'tuple, so the handler catches it.'}],
          'module': 'module4'}},
 {'old': {'text': 'What does this print?',
          'code_snippet': 'def apply(fn, x):\n'
                          '    return fn(x) + 1\n'
                          '\n'
                          'print(apply(lambda v: v * 2, 4))',
          'difficulty': 'medium',
          'choices': [{'text': '9',
                       'is_correct': True,
                       'explanation': 'Correct. Functions are FIRST-CLASS in Python — they can be '
                                      'passed as arguments. `apply` calls `fn(4)` → `4*2 = 8`, '
                                      'then adds 1 → 9.'},
                      {'text': '10',
                       'is_correct': False,
                       'explanation': 'Wrong. The lambda returns `v * 2`, not `v * 2 + 1`. The `+ '
                                      '1` happens once, in `apply`.'},
                      {'text': '8',
                       'is_correct': False,
                       'explanation': 'Wrong. `apply` returns `fn(x) + 1`, not just `fn(x)`.'},
                      {'text': 'TypeError',
                       'is_correct': False,
                       'explanation': 'Wrong. A lambda is just a function object — passing one is '
                                      'perfectly legal.'}],
          'module': 'module4'},
  'new': {'text': 'What does this print?',
          'code_snippet': 'def steps():\n'
                          '    yield 2\n'
                          '    yield 3\n'
                          '\n'
                          'total = 0\n'
                          'for value in steps():\n'
                          '    total += value\n'
                          'print(total)',
          'difficulty': 'medium',
          'choices': [{'text': '5',
                       'is_correct': True,
                       'explanation': 'Correct. Calling the generator function produces the values '
                                      '2 and 3, which the loop adds to `total`.'},
                      {'text': '2',
                       'is_correct': False,
                       'explanation': 'Wrong. The generator yields a second value, 3, before the '
                                      'loop ends.'},
                      {'text': '3',
                       'is_correct': False,
                       'explanation': 'Wrong. `total` accumulates both yielded values rather than '
                                      'keeping only the last one.'},
                      {'text': 'None',
                       'is_correct': False,
                       'explanation': 'Wrong. The loop consumes the yielded values, and the final '
                                      'statement prints the accumulated integer 5.'}],
          'module': 'module4'}},
 {'old': {'text': 'What happens when this runs?',
          'code_snippet': 'x = 3\n'
                          "assert x > 0, 'must be positive'\n"
                          "assert x == 5, 'must be five'\n"
                          "print('ok')",
          'difficulty': 'medium',
          'choices': [{'text': 'AssertionError: must be five',
                       'is_correct': True,
                       'explanation': 'Correct. `assert COND, msg` raises `AssertionError(msg)` '
                                      'when `COND` is falsy. The first assertion passes (3 > 0), '
                                      'but the second fails (3 != 5), so `AssertionError` with the '
                                      'message is raised before `print` can run.'},
                      {'text': 'ok',
                       'is_correct': False,
                       'explanation': 'Wrong. The second `assert` fails, so the program aborts '
                                      'with an exception before reaching `print`.'},
                      {'text': 'AssertionError: must be positive',
                       'is_correct': False,
                       'explanation': "Wrong. The first assertion's condition (`x > 0`) is True, "
                                      'so it raises nothing.'},
                      {'text': 'SyntaxError',
                       'is_correct': False,
                       'explanation': 'Wrong. `assert` is a Python statement, and the `assert '
                                      'COND, MSG` form is valid.'}],
          'module': 'module4'},
  'new': {'text': 'What does this print?',
          'code_snippet': 'try:\n'
                          '    numbers = [1]\n'
                          '    print(numbers[2])\n'
                          'except LookupError:\n'
                          "    print('lookup')",
          'difficulty': 'medium',
          'choices': [{'text': 'lookup',
                       'is_correct': True,
                       'explanation': 'Correct. The invalid list index raises `IndexError`, which '
                                      'inherits from `LookupError`, so the handler runs.'},
                      {'text': 'IndexError',
                       'is_correct': False,
                       'explanation': 'Wrong. An `IndexError` is raised, but the broader '
                                      '`LookupError` handler catches it before it can propagate.'},
                      {'text': '1',
                       'is_correct': False,
                       'explanation': 'Wrong. The list has only index 0; index 2 does not retrieve '
                                      'its sole value.'},
                      {'text': 'nothing',
                       'is_correct': False,
                       'explanation': 'Wrong. The matching handler executes and prints `lookup`.'}],
          'module': 'module4'}},
 {'old': {'text': 'What is the output?',
          'code_snippet': 'square = lambda x: x * x\nprint(square(6))',
          'difficulty': 'easy',
          'choices': [{'text': '36',
                       'is_correct': True,
                       'explanation': 'Correct. The `lambda` defines an anonymous function '
                                      'returning `x * x`, so `square(6)` is 36.'},
                      {'text': '12',
                       'is_correct': False,
                       'explanation': 'Wrong. `x * x` multiplies (6 × 6 = 36); it does not double '
                                      'to 12.'},
                      {'text': 'function',
                       'is_correct': False,
                       'explanation': 'Wrong. `square(6)` CALLS the lambda; printing the name '
                                      'without `()` would show a function object.'},
                      {'text': 'SyntaxError',
                       'is_correct': False,
                       'explanation': 'Wrong. Assigning a lambda to a name is valid Python.'}],
          'module': 'module4'},
  'new': {'text': 'What does this print?',
          'code_snippet': 'def announce():\n'
                          "    print('ready')\n"
                          '\n'
                          'result = announce()\n'
                          'print(result)',
          'difficulty': 'easy',
          'choices': [{'text': 'ready\nNone',
                       'is_correct': True,
                       'explanation': 'Correct. The function prints `ready` and, because it has no '
                                      '`return`, it implicitly returns `None`, which the final '
                                      '`print` displays.'},
                      {'text': 'ready',
                       'is_correct': False,
                       'explanation': 'Wrong. After the function prints `ready`, the program also '
                                      'prints its implicit return value, `None`.'},
                      {'text': 'None\nready',
                       'is_correct': False,
                       'explanation': 'Wrong. The function body runs before its return value is '
                                      'assigned and printed, so `ready` appears first.'},
                      {'text': 'NameError',
                       'is_correct': False,
                       'explanation': 'Wrong. The function and `result` variable are both defined '
                                      'before they are used.'}],
          'module': 'module4'}},
 {'old': {'text': 'What does this print?',
          'code_snippet': 'try:\n'
                          "    raise ValueError('boom')\n"
                          'except Exception as e:\n'
                          '    print(type(e).__name__)',
          'difficulty': 'hard',
          'choices': [{'text': 'ValueError',
                       'is_correct': True,
                       'explanation': 'Correct. `ValueError` is a subclass of `Exception`, so '
                                      '`except Exception` catches it, and `type(e).__name__` is '
                                      'the actual class name "ValueError".'},
                      {'text': 'Exception',
                       'is_correct': False,
                       'explanation': 'Wrong. The caught object keeps its real type (ValueError) '
                                      'even though it was caught via the broader `Exception`.'},
                      {'text': 'boom',
                       'is_correct': False,
                       'explanation': "Wrong. 'boom' is the message (`str(e)`), not the class "
                                      'name.'},
                      {'text': 'Error',
                       'is_correct': False,
                       'explanation': 'Wrong. The class is `ValueError`; there is no plain `Error` '
                                      'type involved.'}],
          'module': 'module4'},
  'new': {'text': 'What does this print?',
          'code_snippet': 'try:\n'
                          '    print(10 / 0)\n'
                          'except ArithmeticError:\n'
                          "    print('arithmetic')\n"
                          'except Exception:\n'
                          "    print('exception')",
          'difficulty': 'hard',
          'choices': [{'text': 'arithmetic',
                       'is_correct': True,
                       'explanation': 'Correct. Division by zero raises `ZeroDivisionError`, a '
                                      'subclass of `ArithmeticError`, so the first matching '
                                      'handler runs.'},
                      {'text': 'exception',
                       'is_correct': False,
                       'explanation': 'Wrong. Although `Exception` also covers the error, Python '
                                      'stops at the earlier matching `ArithmeticError` handler.'},
                      {'text': 'ZeroDivisionError',
                       'is_correct': False,
                       'explanation': 'Wrong. The exception is caught, so its default traceback '
                                      'and class name are not printed.'},
                      {'text': '0',
                       'is_correct': False,
                       'explanation': 'Wrong. Division by zero raises an exception instead of '
                                      'producing a numeric result.'}],
          'module': 'module4'}},
 {'old': {'text': 'What is the output?',
          'code_snippet': 'g = lambda x, y: x * y\nprint(g(3, 4))',
          'difficulty': 'medium',
          'choices': [{'text': '12',
                       'is_correct': True,
                       'explanation': 'Correct. The lambda multiplies its two arguments: 3 * 4 = '
                                      '12.'},
                      {'text': '7',
                       'is_correct': False,
                       'explanation': 'Wrong. The body is `x * y` (multiply), not `x + y`.'},
                      {'text': '34',
                       'is_correct': False,
                       'explanation': 'Wrong. The arguments are multiplied, not concatenated.'},
                      {'text': 'SyntaxError',
                       'is_correct': False,
                       'explanation': 'Wrong. Assigning a lambda to a name and calling it is '
                                      'valid.'}],
          'module': 'module4'},
  'new': {'text': 'What does this print?',
          'code_snippet': 'def sum_to(number):\n'
                          '    if number == 0:\n'
                          '        return 0\n'
                          '    return number + sum_to(number - 1)\n'
                          '\n'
                          'print(sum_to(4))',
          'difficulty': 'medium',
          'choices': [{'text': '10',
                       'is_correct': True,
                       'explanation': 'Correct. The recursive calls add 4 + 3 + 2 + 1, then the '
                                      'base case contributes 0.'},
                      {'text': '4',
                       'is_correct': False,
                       'explanation': 'Wrong. Each call adds its number to the result of another '
                                      'recursive call; it does not return only the first '
                                      'argument.'},
                      {'text': '6',
                       'is_correct': False,
                       'explanation': 'Wrong. This omits 4 from the sum; `sum_to(4)` includes '
                                      'every integer from 4 down to 1.'},
                      {'text': 'RecursionError',
                       'is_correct': False,
                       'explanation': 'Wrong. The argument decreases on every call and reaches the '
                                      'base case at zero.'}],
          'module': 'module4'}},
 {'old': {'text': 'What is the output?',
          'code_snippet': 'def outer():\n'
                          '    x = 1\n'
                          '    def inner():\n'
                          '        nonlocal x\n'
                          '        x = 2\n'
                          '    inner()\n'
                          '    return x\n'
                          'print(outer())',
          'difficulty': 'hard',
          'choices': [{'text': '2',
                       'is_correct': True,
                       'explanation': 'Correct. `nonlocal x` lets inner rebind the enclosing '
                                      "function's x, so outer returns 2."},
                      {'text': '1',
                       'is_correct': False,
                       'explanation': 'Wrong. `nonlocal` makes the assignment affect the outer x, '
                                      'changing it from 1 to 2.'},
                      {'text': 'None',
                       'is_correct': False,
                       'explanation': 'Wrong. outer explicitly returns x, which is 2.'},
                      {'text': 'NameError',
                       'is_correct': False,
                       'explanation': 'Wrong. `nonlocal` correctly binds to the existing x in the '
                                      'enclosing scope.'}],
          'module': 'module4'},
  'new': {'text': 'What does this print?',
          'code_snippet': 'value = 2\n'
                          '\n'
                          'def change(step=3):\n'
                          '    global value\n'
                          '    value += step\n'
                          '    return value\n'
                          '\n'
                          'print(change(), value)',
          'difficulty': 'hard',
          'choices': [{'text': '5 5',
                       'is_correct': True,
                       'explanation': 'Correct. `global value` makes the augmented assignment '
                                      'update the global from 2 to 5; the function returns that '
                                      'same value.'},
                      {'text': '5 2',
                       'is_correct': False,
                       'explanation': 'Wrong. The `global` declaration means the function changes '
                                      'the global variable, so its later value is also 5.'},
                      {'text': '2 5',
                       'is_correct': False,
                       'explanation': 'Wrong. The function returns the updated value 5, and that '
                                      'call is evaluated before the second print argument.'},
                      {'text': 'UnboundLocalError',
                       'is_correct': False,
                       'explanation': 'Wrong. The `global` declaration prevents Python from '
                                      'treating `value` as an uninitialized local variable.'}],
          'module': 'module4'}},
 {'old': {'text': 'What is the output?',
          'code_snippet': 'try:\n'
                          "    raise ValueError('x')\n"
                          'except Exception as e:\n'
                          '    print(type(e).__name__)',
          'difficulty': 'hard',
          'choices': [{'text': 'ValueError',
                       'is_correct': True,
                       'explanation': 'Correct. ValueError is a subclass of Exception, so the '
                                      "handler catches it; `type(e).__name__` is 'ValueError'."},
                      {'text': 'Exception',
                       'is_correct': False,
                       'explanation': 'Wrong. `type(e)` is the actual class raised, ValueError, '
                                      'not the base class named in `except`.'},
                      {'text': 'x',
                       'is_correct': False,
                       'explanation': "Wrong. 'x' is the message; `__name__` gives the exception "
                                      'class name.'},
                      {'text': 'Error',
                       'is_correct': False,
                       'explanation': "Wrong. The class is ValueError; there is no plain 'Error' "
                                      'here.'}],
          'module': 'module4'},
  'new': {'text': 'What does this print?',
          'code_snippet': 'try:\n'
                          "    int('PCEP')\n"
                          'except Exception:\n'
                          "    print('general')\n"
                          'except ValueError:\n'
                          "    print('specific')",
          'difficulty': 'hard',
          'choices': [{'text': 'general',
                       'is_correct': True,
                       'explanation': "Correct. `int('PCEP')` raises `ValueError`, but the earlier "
                                      '`Exception` handler also matches it and runs first.'},
                      {'text': 'specific',
                       'is_correct': False,
                       'explanation': 'Wrong. Python selects the first matching handler; the '
                                      'broader `Exception` handler appears before `ValueError`.'},
                      {'text': 'general\nspecific',
                       'is_correct': False,
                       'explanation': 'Wrong. Only one matching `except` suite executes for an '
                                      'exception.'},
                      {'text': 'ValueError',
                       'is_correct': False,
                       'explanation': 'Wrong. The exception is caught by the first handler, so it '
                                      'does not propagate.'}],
          'module': 'module4'}},
 {'old': {'text': 'What is the output?',
          'code_snippet': 'print((lambda x: x * x)(5))',
          'difficulty': 'medium',
          'choices': [{'text': '25',
                       'is_correct': True,
                       'explanation': 'Correct. The lambda squares its argument; called with 5 it '
                                      'returns 25.'},
                      {'text': '10',
                       'is_correct': False,
                       'explanation': 'Wrong. The body is `x * x` (squaring), not `x + x`.'},
                      {'text': '5',
                       'is_correct': False,
                       'explanation': 'Wrong. The lambda is immediately called with 5, returning 5 '
                                      '* 5.'},
                      {'text': '<function>',
                       'is_correct': False,
                       'explanation': 'Wrong. The lambda is invoked right away, so its result is '
                                      'printed.'}],
          'module': 'module4'},
  'new': {'text': 'What does this print?',
          'code_snippet': 'def numbers():\n'
                          '    yield 2\n'
                          '    yield 5\n'
                          '\n'
                          'values = []\n'
                          'for number in numbers():\n'
                          '    values.append(number)\n'
                          'print(values)',
          'difficulty': 'medium',
          'choices': [{'text': '[2, 5]',
                       'is_correct': True,
                       'explanation': 'Correct. The generator yields 2 and then 5, and the loop '
                                      'appends each yielded value to the list.'},
                      {'text': '[5, 2]',
                       'is_correct': False,
                       'explanation': 'Wrong. Generator values are produced in execution order: '
                                      'the first `yield` supplies 2 before the second supplies 5.'},
                      {'text': '2\n5',
                       'is_correct': False,
                       'explanation': 'Wrong. The loop appends values without printing them; one '
                                      'list is printed after the loop finishes.'},
                      {'text': '[]',
                       'is_correct': False,
                       'explanation': 'Wrong. Iterating over `numbers()` executes both `yield` '
                                      'statements, so two values are appended.'}],
          'module': 'module4'}},
 {'old': {'text': 'What happens when this runs?',
          'code_snippet': "print('abc' + 3)",
          'difficulty': 'easy',
          'choices': [{'text': 'abc3',
                       'is_correct': False,
                       'explanation': 'Wrong. Python does NOT auto-convert between `str` and `int` '
                                      "for the `+` operator. To get this output you'd need `'abc' "
                                      "+ str(3)` or an f-string `f'abc{3}'`."},
                      {'text': 'TypeError',
                       'is_correct': True,
                       'explanation': 'Correct. `+` requires operands of compatible types. `str + '
                                      'str` concatenates, `int + int` adds, but `str + int` raises '
                                      '`TypeError: can only concatenate str (not "int") to str`.'},
                      {'text': 'abcabcabc',
                       'is_correct': False,
                       'explanation': "Wrong. That would be `'abc' * 3` (repetition). With `+` the "
                                      'operand types must match.'},
                      {'text': '6',
                       'is_correct': False,
                       'explanation': 'Wrong. Python does not sum character codes — and even if it '
                                      'did, this expression never reaches that point because of '
                                      'the type mismatch.'}],
          'module': 'module1'},
  'new': {'text': 'What happens when this runs?',
          'code_snippet': "print('abc' + 3)",
          'difficulty': 'easy',
          'choices': [{'text': 'abc3',
                       'is_correct': False,
                       'explanation': 'Wrong. Python does not auto-convert between `str` and `int` '
                                      'for `+`. To get this output, convert the number explicitly: '
                                      "`'abc' + str(3)`."},
                      {'text': 'TypeError',
                       'is_correct': True,
                       'explanation': 'Correct. `+` requires operands of compatible types. `str + '
                                      'str` concatenates, `int + int` adds, but `str + int` raises '
                                      '`TypeError: can only concatenate str (not "int") to str`.'},
                      {'text': 'abcabcabc',
                       'is_correct': False,
                       'explanation': "Wrong. That would be `'abc' * 3` (repetition). With `+` the "
                                      'operand types must match.'},
                      {'text': '6',
                       'is_correct': False,
                       'explanation': 'Wrong. Python does not sum character codes — and even if it '
                                      'did, this expression never reaches that point because of '
                                      'the type mismatch.'}],
          'module': 'module1'}},
 {'old': {'text': 'Which type does `3 / 2` evaluate to?',
          'code_snippet': '',
          'difficulty': 'easy',
          'choices': [{'text': 'int',
                       'is_correct': False,
                       'explanation': 'Wrong. In Python 3, `/` always returns a float, even when '
                                      'both operands divide evenly. Python 2 used to return int '
                                      'for int/int, but that was removed.'},
                      {'text': 'float',
                       'is_correct': True,
                       'explanation': 'Correct. In Python 3, `/` (true division) always returns '
                                      '`float`, regardless of operand types. `3 / 2` is `1.5`.'},
                      {'text': 'complex',
                       'is_correct': False,
                       'explanation': 'Wrong. `complex` results come from operations involving '
                                      'complex numbers (written with `j`, e.g. `3 + 2j`). Division '
                                      'of two real ints gives `float`.'},
                      {'text': 'bool',
                       'is_correct': False,
                       'explanation': 'Wrong. `bool` is returned by comparisons and logical '
                                      'operators, not arithmetic operators.'}],
          'module': 'module1'},
  'new': {'text': 'Which type does `3 / 2` evaluate to?',
          'code_snippet': '',
          'difficulty': 'easy',
          'choices': [{'text': 'int',
                       'is_correct': False,
                       'explanation': 'Wrong. In Python 3, `/` always returns a float, even when '
                                      'both operands divide evenly. Python 2 used to return int '
                                      'for int/int, but that was removed.'},
                      {'text': 'float',
                       'is_correct': True,
                       'explanation': 'Correct. In Python 3, `/` (true division) always returns '
                                      '`float`, regardless of operand types. `3 / 2` is `1.5`.'},
                      {'text': 'str',
                       'is_correct': False,
                       'explanation': 'Wrong. Division of numeric operands returns a numeric '
                                      'value, not a string.'},
                      {'text': 'bool',
                       'is_correct': False,
                       'explanation': 'Wrong. `bool` is returned by comparisons and logical '
                                      'operators, not arithmetic operators.'}],
          'module': 'module1'}},
 {'old': {'text': 'What is `abs(-3.5)`?',
          'code_snippet': 'print(abs(-3.5))',
          'difficulty': 'easy',
          'choices': [{'text': '3.5',
                       'is_correct': True,
                       'explanation': 'Correct. `abs` returns the absolute (non-negative) value of '
                                      'a number, preserving its type: `abs(-3.5)` is `3.5`, a '
                                      'float.'},
                      {'text': '-3.5',
                       'is_correct': False,
                       'explanation': 'Wrong. `abs` removes the sign; it never returns a negative '
                                      'number.'},
                      {'text': '3',
                       'is_correct': False,
                       'explanation': 'Wrong. `abs` does not change the numeric type. The input is '
                                      'a float, so the output is a float.'},
                      {'text': 'TypeError',
                       'is_correct': False,
                       'explanation': 'Wrong. `abs` accepts int, float, and complex without '
                                      'error.'}],
          'module': 'module1'},
  'new': {'text': 'What is `abs(-3.5)`?',
          'code_snippet': 'print(abs(-3.5))',
          'difficulty': 'easy',
          'choices': [{'text': '3.5',
                       'is_correct': True,
                       'explanation': 'Correct. `abs` returns the absolute (non-negative) value of '
                                      'a number, preserving its type: `abs(-3.5)` is `3.5`, a '
                                      'float.'},
                      {'text': '-3.5',
                       'is_correct': False,
                       'explanation': 'Wrong. `abs` removes the sign; it never returns a negative '
                                      'number.'},
                      {'text': '3',
                       'is_correct': False,
                       'explanation': 'Wrong. `abs` does not change the numeric type. The input is '
                                      'a float, so the output is a float.'},
                      {'text': 'TypeError',
                       'is_correct': False,
                       'explanation': 'Wrong. `abs` accepts real numeric input such as integers '
                                      'and floats.'}],
          'module': 'module1'}},
 {'old': {'text': 'What does this print?',
          'code_snippet': 'def counter():\n'
                          '    count = 0\n'
                          '    def bump():\n'
                          '        count = count + 1\n'
                          '        return count\n'
                          '    return bump\n'
                          '\n'
                          'c = counter()\n'
                          'print(c())',
          'difficulty': 'hard',
          'choices': [{'text': '1',
                       'is_correct': False,
                       'explanation': 'Wrong. This would require `nonlocal count` inside `bump`. '
                                      'Without it, `count = count + 1` tries to read a LOCAL '
                                      '`count` that has not been assigned yet, raising '
                                      'UnboundLocalError.'},
                      {'text': 'UnboundLocalError',
                       'is_correct': True,
                       'explanation': 'Correct. Because `count` is ASSIGNED inside `bump`, Python '
                                      'treats it as a local variable throughout the function. '
                                      "`count + 1` then tries to READ the local before it's "
                                      'defined, raising `UnboundLocalError`. The fix is `nonlocal '
                                      'count`.'},
                      {'text': '0',
                       'is_correct': False,
                       'explanation': 'Wrong. No such fallback occurs. Read-before-write on a '
                                      'local name is an error.'},
                      {'text': 'NameError',
                       'is_correct': False,
                       'explanation': 'Wrong. The specific error is `UnboundLocalError` (a '
                                      'subclass of NameError), raised at the moment `count` is '
                                      'read.'}],
          'module': 'module4'},
  'new': {'text': 'What does this print?',
          'code_snippet': 'def counter():\n'
                          '    count = 0\n'
                          '    def bump():\n'
                          '        count = count + 1\n'
                          '        return count\n'
                          '    return bump\n'
                          '\n'
                          'c = counter()\n'
                          'print(c())',
          'difficulty': 'hard',
          'choices': [{'text': '1',
                       'is_correct': False,
                       'explanation': 'Wrong. This would require `bump` to update the value from '
                                      'the enclosing scope. As written, the assignment makes '
                                      '`count` local to `bump`.'},
                      {'text': 'UnboundLocalError',
                       'is_correct': True,
                       'explanation': 'Correct. Because `count` is assigned inside `bump`, Python '
                                      'treats it as a local variable throughout that function. The '
                                      'right-hand side then reads the local before it has a value, '
                                      'raising `UnboundLocalError`.'},
                      {'text': '0',
                       'is_correct': False,
                       'explanation': 'Wrong. No such fallback occurs. Read-before-write on a '
                                      'local name is an error.'},
                      {'text': 'NameError',
                       'is_correct': False,
                       'explanation': 'Wrong. The specific error is `UnboundLocalError` (a '
                                      'subclass of NameError), raised at the moment `count` is '
                                      'read.'}],
          'module': 'module4'}}]


def _replace(apps, schema_editor, source, target):
    Question = apps.get_model('quiz', 'Question')
    alias = schema_editor.connection.alias
    source_rows = Question.objects.using(alias).filter(
        module=source['module'],
        text=source['text'],
        code_snippet=source['code_snippet'],
    )
    if source_rows.count() > 1:
        raise RuntimeError(f"Multiple questions match {source['text']!r}")
    question = source_rows.first()
    if question is None:
        # Fresh databases run data migrations before the seed command. A database
        # already migrated in a staged release may also contain the target row.
        return

    choices = list(question.choices.using(alias).order_by('id'))
    if len(choices) != len(target['choices']):
        raise RuntimeError(
            f"Question id={question.id} has {len(choices)} choices; "
            f"expected {len(target['choices'])}"
        )
    actual_choices = [
        {
            'text': answer.text,
            'is_correct': answer.is_correct,
            'explanation': answer.explanation,
        }
        for answer in choices
    ]
    if question.difficulty != source['difficulty'] or actual_choices != source['choices']:
        raise RuntimeError(
            f'Question id={question.id} differs from the reviewed source; '
            'refusing to overwrite it'
        )

    question.text = target['text']
    question.code_snippet = target['code_snippet']
    question.difficulty = target['difficulty']
    question.updated_at = timezone.now()
    question.save(
        using=alias,
        update_fields=['text', 'code_snippet', 'difficulty', 'updated_at'],
    )
    for answer, replacement in zip(choices, target['choices'], strict=True):
        answer.text = replacement['text']
        answer.is_correct = replacement['is_correct']
        answer.explanation = replacement['explanation']
        answer.save(
            using=alias,
            update_fields=['text', 'is_correct', 'explanation'],
        )


def replace_out_of_scope_constructs(apps, schema_editor):
    for replacement in REPLACEMENTS:
        _replace(apps, schema_editor, replacement['old'], replacement['new'])


def restore_out_of_scope_constructs(apps, schema_editor):
    for replacement in REPLACEMENTS:
        _replace(apps, schema_editor, replacement['new'], replacement['old'])


class Migration(migrations.Migration):
    dependencies = [('quiz', '0007_add_question_objective')]
    operations = [
        migrations.RunPython(
            replace_out_of_scope_constructs,
            restore_out_of_scope_constructs,
        )
    ]
