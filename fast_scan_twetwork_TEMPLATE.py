# python=3.7

__author__ = 'Marc Maxmeister'
__license__ = 'MIT'
__about__ = 'a fast, standalone recursive twitter network scanning function. Feed it twitter's API details and a core screen_name, and it will generate three folders with all the data to create a network map'

import tweepy # this is NOT part of the standard python library.
import time
import os
import sys
import json
import argparse
from bson import json_util
from collections import Counter
import math


# this can take one twitter name or a list of names. 
SCREEN_NAMES = ['opencontracting']
WORDLIST = ['open contract','government','contracting','contracts']

FILTER_BY_WORDLIST = False
RECURSE_LIMIT = 12
TWEETS = 400 # per user, or readds 3X (1200 tweets) for the original core users
FOLLOWING_DIR = 'following'
MAPS_DIR = 'maps' # used later
TWITTER_USERS_DIR = 'twitter-users'
STOP_WORDS = ["a","about","above","according","across","actually","adj","after","afterwards","again","against","all","almost","alone","along",
                 "already","also","although","always","among","amongst","an","and","another","any","anyhow","anyone",
                 "anything","anywhere","are","aren't","around","as","at","b","be","became","because","become","becomes","becoming","been","before","beforehand","begin","behind","being","below","beside",
                 "besides","between","beyond","both","but","by","c","can","can't","cannot","caption","co","co.","could","couldn't","d","did","didn't","do","does","doesn't","don't","down","during","e","each","eg","eight","eighty","either","else","elsewhere","end","ending","enough","etc","even","ever","every","everyone","everything","everywhere","except","f","few",
                 "first","for","found","from","further","g","h","had","has","hasn't","have","haven't","he","he'd","he'll","he's","hence","her","here","here's","hereafter","hereby","herein","hereupon",
                 "hers","herself","him","himself","his","how","however","hundred","i","i'd","i'll","i'm","i've","ie","if","in","inc.","indeed","instead","into","is","isn't","it","it's","its","itself","j","k","l","last","later","latter","latterly","least","less","let","let's","like","likely","ltd","m","made","make","makes","many","maybe","me","meantime","meanwhile","might","miss","more","moreover","most","mostly","mr","mrs","much","must","my","myself","n","namely","neither","never","nevertheless","next","nine",
                 "ninety","no","nobody","none","nonetheless","noone","nor","not","nothing","now","nowhere","o","of","off","often","on","once",
                 "one","one's","only","onto","or","other","others","otherwise","our","ours","ourselves","out","over","overall","own","p","per","perhaps","q","r","rather","recent","recently","s","same","seem","seemed","seeming","seems","seven","several","she","she'd","she'll","she's","should","shouldn't","since","so","some","somehow","someone","something","sometime","sometimes","somewhere","still","such","t","taking","than","that","that'll","that's","that've","the","their","them","themselves","then",
                 "thence","there","there'd","there'll","there're","there's","there've","thereafter","thereby","therefore",
                 "therein","thereupon","these","they","they'd","they'll","they're",
                 "they've","thirty","this","those","though","three","through","throughout","thru","thus","to","together","too","toward","towards","u","under","unless","unlike","unlikely","until","up","upon","us","used","using","v","very","via","w","was","wasn't","we","we'd","we'll","we're","we've","well","were","weren't","what","what'll","what's","what've","whatever","when","whence","whenever","where","where's","whereafter","whereas","whereby","wherein","whereupon","wherever","whether","which",
                 "while","whither","who","who'd","who'll","who's","whoever","whole","whom","whomever","whose","why","will","with",
                 "within","without","won't","would","wouldn't","x","y","yes","yet","you","you'd","you'll","you're","you've","your","yours","yourself","yourselves","z",
                 "help","people","dont","go","am","get","got","went","nbsp", "rt"]
# FRIENDS_OF_FRIENDS_LIMIT = 50 # does this for ocp's first friend, instead of finish inner circle first.
# SHARED_FRIENDS_ONLY = True # faster mapping, excludes friends that don't point back to the source.

if not os.path.exists(FOLLOWING_DIR):
    os.mkdir(FOLLOWING_DIR)
if not os.path.exists(MAPS_DIR):
    os.mkdir(MAPS_DIR)
if not os.path.exists(TWITTER_USERS_DIR):
    os.mkdir(TWITTER_USERS_DIR)

# The consumer keys can be found on your application's Details
# page located at https://dev.twitter.com/apps (under "OAuth settings")
# https://apps.twitter.com/app/1563721/show
CONSUMER_KEY = '' 
CONSUMER_SECRET = ''

# The access tokens can be found on your applications's Details
# page located at https://dev.twitter.com/apps (located
# under "Your access token")
ACCESS_TOKEN = ''
ACCESS_TOKEN_SECRET = ''

# ============== OAuth Authentication ==================
# This mode of authentication is the new preferred way
# of authenticating with Twitter.
auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
auth.set_access_token(ACCESS_TOKEN, ACCESS_TOKEN_SECRET)

api = tweepy.API(auth, wait_on_rate_limit=True, wait_on_rate_limit_notify=True)

# MUST use user_ids in mapping steps until last part - can replace a few of these with screen_names
global_lookup = {} # screen_name --> real_name
global_visited = []
   
def fast_scan(names=[], unique_mentions_per_user=TWEETS, filter_by_wordlist=False, iteration=1, recurse_limit=RECURSE_LIMIT):
    """ must avoid: user.followers_ids(count=5000), # limit 15/15min
    proxy: read last 1000 tweets and generate an id_list for all users mentioned in any tweets
    optional: limit to tweets / usernames that include one word from WORDLIST
    always: scores users' relevance based on WORDLIST
    """

    def mentions(tweet, unames=Counter()):
        if len(tweet["entities"]["user_mentions"]) > 0: # key missing if restricted/protected account?
            for mention in tweet["entities"]["user_mentions"]:
                unames[mention['screen_name']] += 1
                global_lookup[mention['screen_name']] = mention['name']
        return unames

    def score_user(follower_data):
        string_of_text = ' '.join(follower_data['tweets']).lower()
        bag_of_words = Counter(string_of_text.split())
        bag_of_words = Counter({k:v for k,v in bag_of_words.items() if v > 1 and k not in STOP_WORDS})
        if ( len([word for word in WORDLIST if word in bag_of_words]) > 0 or
            len([word for word in WORDLIST if word in follower_data['description']]) > 0 or
            len([word for word in WORDLIST if word in follower_data['screen_name']]) > 0
            ):
            decided = True
        else:
            decided = False
        
        follower_data['follow_again'] = decided
        follower_data['keywords'] = [k for k,v in bag_of_words.most_common(15) if v >= 5 and len(k) > 3]
        # weight by percent relevant updates, relevant description, relevant screen name
        score = 0
        for word in WORDLIST:
            for tweet in follower_data['tweets']:                
                if word in tweet:
                    score += 1
            if word in follower_data['description']:
                score += 5
            if word in follower_data['screen_name']:
                score += 5
        if follower_data['friends_count'] > 0:
            score += math.log10(follower_data['friends_count']) * (1/100.)
        if follower_data['followers_count'] > 0:
            score += math.log10(follower_data['followers_count']) * (1/100.)
        if follower_data['retweeted_count'] > 0:
            score += math.log10(follower_data['retweeted_count']) * (1/100.)
        if follower_data['listed_count'] > 0:
            score += math.log10(follower_data['listed_count']) * (1/10.)
        follower_data['weight'] = int(score)
        #print 'n={0}, {1}: {2} = {3}'.format(len(follower_data['tweets']), decided, bag_of_words.most_common(5), int(score))
        #self.screen_weight[follower_data['screen_name']] = int(score)
        return follower_data # revised now

    # scan each of a list of top level screen_names and build a global_lookup.
    user = {}
    recurse_candidates = Counter()
    for centre in names:
        if centre in global_visited:
            continue
        data = tweepy.Cursor(api.user_timeline, screen_name=centre, count=200).items() # api max count is 200 per call; call rate limit is 1500/15min
        mentions_count = 0
        tweets_processed = 0
        try:
            for TWEET in data: # will keep going indefinitely, until limit reached
                tweet = TWEET._json
                retweeted = tweet["retweeted_status"]["retweet_count"] if tweet.get("retweeted_status") and tweet["retweeted_status"].get('retweet_count') else 0
                if tweet['user']['screen_name'] not in user:
                    user[tweet['user']['screen_name']] = {
                    'screen_name': tweet['user']['screen_name'],
                    'name': tweet['user']['name'],
                    'id': tweet['user']['id'],
                    'description': tweet['user']['description'],
                    'profile_location': tweet['user']['location'],
                    'url': tweet['user']['url'],                
                    "friends_count": tweet["user"]["friends_count"],
                    "followers_count": tweet["user"]["followers_count"],
                    'retweeted_count': retweeted,
                    "listed_count": tweet["user"]["listed_count"],
                    'statuses_count': tweet["user"]["statuses_count"],
                    'mentions': mentions(tweet, Counter()), # append mentions here, and adds to global lookup -- REALLY REALLY important to pass an empty Counter each time, else the same counter lives "between" each user and doesn't reset.
                    'tweets': [tweet['text']],
                    'weight': 0,
                    }                
                else: # append
                    mentioned_names = user[tweet['user']['screen_name']]['mentions']
                    user[tweet['user']['screen_name']]['mentions'] = mentions(tweet, mentioned_names)
                    user[tweet['user']['screen_name']]['tweets'].append(tweet['text'])
                    if tweet.get("retweeted_status") and tweet["retweeted_status"].get('retweet_count') > 0:
                        user[centre]['retweeted_count'] += tweet["retweeted_status"]['retweet_count']                    
                mentions_count = len(user[tweet['user']['screen_name']]['mentions'])        
                tweets_processed += 1
                #if len([WORD for WORD in WORDLIST if WORD in tweet['text'].lower()]) > 0:
                #    if tweets_processed % 125 == 0: # limit overload
                #        print tweets_processed, '---', tweet['text']
                #if tweets_processed % 200 == 0 and tweets_processed > 0:
                #    print u"{0}: {1} tweets ---> {2} mentions".format(centre, tweets_processed, mentions_count)
                if (iteration == 1 and centre == names[0] and # the first name in first round only
                    (mentions_count > 3*unique_mentions_per_user or tweets_processed >= 6000)                    
                    ):
                    print('        {0} tweets processed for CORE {2}, retweets: {1}'.format(tweets_processed, user[centre]['retweeted_count'], mentions_count, unique_mentions_per_user, centre))
                    user[centre] = score_user(user[centre]) # adds more stuff based on all tweets and data
                    if filter_by_wordlist == True and WORDLIST != []:
                        for tweet in user[tweet['user']['screen_name']]['tweets']:
                            if not set(tweet.split()) & set(WORDLIST): # not any overlap
                                user.pop(centre) # removes this person entirely if not matching
                                print( 'tested and removed {0}'.format(centre))
                    break                                    
                if ( not (iteration == 1 and centre == names[0]) and 
                     (mentions_count > unique_mentions_per_user or tweets_processed >= 3000)
                    ):
                    print( '        {0} tweets processed for {2}, retweets: {1}'.format(tweets_processed, user[centre]['retweeted_count'], mentions_count, unique_mentions_per_user, centre))
                    user[centre] = score_user(user[centre]) # adds more stuff based on all tweets and data
                    if filter_by_wordlist == True and WORDLIST != []:
                        for tweet in user[tweet['user']['screen_name']]['tweets']:
                            if not set(tweet.split()) & set(WORDLIST): # not any overlap
                                user.pop(centre) # removes this person entirely if not matching
                                print( 'tested and removed {0}'.format(centre))
                    break
        except tweepy.TweepError as e:
            print (e.api_code)
            print (e.reason)
            continue
        # function returns: global_lookup and list of users to save
        # SAVE this centre user to disk with 'mentions' list of friends for recursive part later.
        # it is possible to feed a list of the key mentioned accounts into this function recursively.        
        try:
            userfname = os.path.join(TWITTER_USERS_DIR, str(user[centre]['screen_name']) + '.json')
            this_user = user[centre] # mentions will be a dict instead of a counter in file.            
            with open(userfname, 'w') as outf:                
                outf.write(json.dumps(this_user, indent=2, default=json_util.default))
        except Exception as e:
            import traceback
            print( traceback.format_exc())
            print( e, centre, 'JSON NOT SAVED')
            #import pdb;pdb.set_trace()

        # SAVE A FOLLOWING_DIR CSV of centre-mention-links for mapping.
        #params = (friend.id, friend.screen_name, friend.name)
        best_friends = [k for k,v in this_user['mentions'].most_common() if v >= 3] # at least 3 mentions
        print( '        Found {0} best friends for {1} (out of {2})...'.format(len(best_friends), this_user['screen_name'], len(this_user['mentions'])))
        
        all_friends = [k for k,v in this_user['mentions'].most_common(100)] # for saving a larger network        
        friends_list = [(-1,friend,-1) for friend in all_friends] # screen_names
        userfname = os.path.join(FOLLOWING_DIR, enc(this_user['screen_name']) + '.csv')
        with open(userfname, 'w') as outf:
            for params in friends_list:
                outf.write('%s\t%s\t%s\n' % params)        
        for best_friend in all_friends:
            # here, you can add +1 per user that ranks them as best, or +N for number of times mentioned across all users
            recurse_candidates[best_friend] += this_user['mentions'][best_friend] # filter among all users in this layer later
        global_visited.append(centre)

    # ======= recursive part... =========
    # choose the best names to follow from among all users' best_friends.
    if iteration < recurse_limit:
        print("")
        print( 'next round of core names to study:')
        print( [u"{0} {1}".format(k,v) for k,v in recurse_candidates.most_common(64) if k not in global_visited and v >= 2]) #### FUTURE: customize the number of good candidates to keep per iteration as kwarg ####
        recurse_candidates = [k for k,v in recurse_candidates.most_common(64) if k not in global_visited and v >= 2]
        print( u"finished iteration {0} out of {1} total: global_lookup has {2} names.".format(iteration, recurse_limit, len(global_lookup)))
        print("")
        fast_scan(names=recurse_candidates,
                         unique_mentions_per_user=unique_mentions_per_user,
                         filter_by_wordlist=filter_by_wordlist,
                         iteration=iteration+1,
                         recurse_limit=recurse_limit)
    else:
        print( u"finished iteration {0} out of {1} total: global_lookup has {2} names.".format(iteration, recurse_limit, len(global_lookup)))
        return user


def save_lookups():
    print(len(global_lookup),'len(global_lookup)', len(global_visited), 'len(global_visited)')
    with open(r'{0}\global_loookup_{1}.csv'.format(MAPS_DIR,SCREEN_NAMES),'wb') as f:
        import json
        f.write(json.dumps(global_lookup))
    with open(r'{0}\global_visited_{1}.csv'.format(MAPS_DIR,SCREEN_NAMES),'wb') as f:
        import json
        f.write(json.dumps(global_visited))
    print('files saved')


if __name__ == '__main__':
    fast_scan(names=SCREEN_NAMES, filter_by_wordlist=FILTER_BY_WORDLIST)
    save_lookups()
