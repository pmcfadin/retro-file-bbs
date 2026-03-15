/* atob: version 4.0
 *
 *
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

uchar vers[]="4.0 jet 09/01/93";
char tmp_name[17];
unsigned long Ceor = 0;
unsigned long Csum = 0;
unsigned long Crot = 0;
unsigned long word = 0;
unsigned int bcount=0;

union {
	unsigned long word;
	unsigned char auchar[4];
	} ublock;
FILE *fin, *fout;

void fatal(char * msg){
	printf("\aATOB: ERROR: %s\n", msg);
	_exit(1);
}

#define DE(c) ((c) - '!')

void decode(uchar c){
	if (c == 'z'){
		if (bcount != 0)
			fatal("bcount synchronization error");
		else {
			byteout(0);
			byteout(0);
			byteout(0);
			byteout(0);
		}
	} 
	else
	if ((c >= '!') && (c < ('!' + 85))){
		if (bcount == 0){
			ublock.word = DE(c);
			++bcount;
		} 
		else
		if (bcount < 4){
			ublock.word *= 85;
			ublock.word += DE(c);
			++bcount;
		}
		else {
			ublock.word = ublock.word*85 + DE(c);
			byteout(ublock.auchar[3]);
			byteout(ublock.auchar[2]);
			byteout(ublock.auchar[1]);
			byteout(ublock.auchar[0]);
			ublock.word = 0;
			bcount = 0;
		}
	}
	else
		fatal("illegal character in input stream");
}

FILE *tmp_file;

byteout(c) {
	Ceor ^= c;
	Csum += c;
	Csum += 1;
	if ((Crot & 0x80000000)){
		Crot <<= 1;
		Crot += 1;
	}
	else
		Crot <<= 1;
	Crot += c;
	if((putc(c, tmp_file))==EOF)
		fatal(strcat("write error on file ", tmp_name));
}

main(int argc, char *argv[])
{
	register int c, *tempbuf;
	char buf[100];
	char *tmppath;
	unsigned long n1, n2, oeor, osum, orot;

	if (argc != 3){
		printf("\a Bad args to ATOB!\n");
		printf("Usage: ATOB [u:][d:]textfile.ext [u:][d:]binfile.ext\n");
		printf("[] are optional but must be in above order if included\n");
		_exit(2);
	}

	/* place tmp file in TEMP or TMPDIR (presumably a ramdisk?) if possible */
	if((fin = fopen(argv[1],"r"))==NULL)
		fatal(strcat("I cannot find ",argv[1]));
	if((tmppath=getenv("TEMP"))==NULL)
		if((tmppath=getenv("TMPDIR"))==NULL)
			tmppath="";
	strcpy(tmp_name,strcat(tmppath,"atobtemp.$$$"));
	tmp_file = fopen(tmp_name,"wb");
	if (tmp_file == NULL)
		fatal(strcat("couldn't open tmp file ", tmp_name));
	printf("Ascii TO Binary Filter Version %s.\n",vers); 
	printf("Converting %s to %s\n",argv[1],argv[2]);
	/*search for header line*/
	for (;;) {
		if (fgets(buf, sizeof(buf), fin) == NULL)
			fatal("input file has no btoa Begin line!");
		if ((strcmp(buf, "xbtoa Begin\n"))==0)
			break;
	}
	while ((c = getc(fin)) != EOF) {
		if (c == '\n')
			continue;
		else if (c == 'x')
			break;
		else
			decode(c);
	}
	if (fscanf(fin,"btoa End N %ld %lx E %lx S %lx R %lx\n",
		&n1, &n2, &oeor, &osum, &orot) != 5)
			fatal("scanf failure on sumcheck line");
	if ((n1 != n2) || (oeor != Ceor) || (osum != Csum) || (orot != Crot))
		fatal("sumcheck values don't match");
	else {	/*copy OK tmp file to fout*/
		fclose(tmp_file); /*Original used to rewind(tmp_file) but
* that causes problems as I can't do a "w+b" file mode with Hi-Tech C:-( */
		freopen(tmp_name,"rb",tmp_file);
		fout = fopen(argv[2],"wb");
		tempbuf = malloc(128);
		while(!feof(tmp_file)) {
		fread(tempbuf,128,1,tmp_file); /*Orginal used getc & putc*/
		fwrite(tempbuf,128,1,fout);
		}
		fclose(tmp_file);
		unlink(tmp_name);
	}
}

