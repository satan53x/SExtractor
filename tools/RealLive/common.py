def printHex(b):
	c = -1
	for i in b:
		c += 1
		if c % 16 == 0: print('')
		print(f'{i:02X} ', end='')
	print('')