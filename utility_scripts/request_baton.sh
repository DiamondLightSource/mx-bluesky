#!/bin/bash
SHOW=0
for option in "$@"; do
    case $option in
        --help|-h)
            echo "`basename $0` [options] <Hyperion|GDA>"
            cat <<END
Request the baton to or from Hyperion

Options:
  --help                  This help
  --show		  Show current baton holder

By default this script will start an Hyperion server unless the --no-start flag is specified.
END
            exit 0
            ;;
	--show)
	    SHOW=1
	    shift
	    ;;
        -*|--*)
            echo "Unknown option ${option}. Use --help for info on option usage."
            exit 1
            ;;
    esac
done

PV=BL03I-CS-BATON-01:REQUESTED_USER
NEW_HOLDER=$1
if [ $SHOW = 1 ]; then
	caget $PV
else
	caput $PV $NEW_HOLDER
fi
