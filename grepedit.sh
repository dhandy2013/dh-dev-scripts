# put this function in your .bashrc, it will invoke your editor with the last
# file found in the grep results
#
# grep -r stringimlookingfor *| grepedit

grepedit ()
{
    read output;
    $EDITOR `echo $output| tail -1 | cut -d":" -f1`
}


